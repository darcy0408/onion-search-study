#!/usr/bin/env python3
"""Study 1 harness: query onion search engines, record structured results.

Reimplements Robin's fetch step deliberately. Robin's fetch_search_results()
returns [] for non-200, timeout AND exception alike, which conflates "zero
results" with "engine failed" -- the exact confound this study must avoid.
Here, status / latency / error / n_results are recorded as separate fields.

Parsing reuses Robin's own helpers so the result set matches what Robin sees.

RECORDS TITLES AND URLS ONLY. Never fetches a result page body.
"""
import argparse
import json
import os
import random
import secrets
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urlparse

sys.path.insert(0, "/app")
import requests
from bs4 import BeautifulSoup
import search as robin

# Raw output holds result titles and .onion addresses: data/raw is gitignored.
# Do not publish it.
DATA_DIR = os.path.dirname(os.path.abspath(__file__)) + "/data/raw"
ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"

# ---------- query conditions ----------
# TARGET: services with a known, genuine onion presence -> should match if the
#         engine actually indexes.
TARGET = [
    "SecureDrop", "ProPublica", "Riseup", "Debian", "DuckDuckGo",
    "Tor Project", "BBC", "OnionShare", "ProtonMail", "Whonix",
]
# NULL: random strings that cannot match anything. Any result is noise by
#       definition. This is the study's control condition.
COMMON = [
    "market", "forum", "news", "search", "shop",
    "email", "wiki", "hosting", "blog", "library",
]


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def make_null_queries(n, length=12):
    return ["".join(secrets.choice(ALPHABET) for _ in range(length)) for _ in range(n)]


def tor_exit_ip():
    """Best-effort current Tor exit IP, for per-run provenance. Never fatal."""
    try:
        s = robin.get_tor_session()
        r = s.get("https://check.torproject.org/api/ip", timeout=30)
        return r.json().get("IP")
    except Exception:
        return None


def classify_block(text):
    """Explain a ZERO-RESULT 200-OK page: JS shell, CAPTCHA wall, or genuinely empty.

    Only ever called when parsing yielded no results. Calling it on every page
    produced false positives: Excavator serves real results on a page whose own
    copy says "learn how JavaScript is disabled", and was wrongly discarded.
    A page that yields results is by definition not blocked, so parse-first and
    use these markers only to explain an empty one.
    """
    t = (text or "").lower()
    captcha_markers = (
        "solve this captcha",
        "solve the following",
        "solve this simple",
        "required to solve",
        "- captcha",
        "– captcha",
    )
    if any(m in t for m in captcha_markers):
        return "blocked_captcha"
    js_markers = (
        "non-javascript version",
        "javascript is disabled in your browser",
        "please enable javascript",
        "search feature will not work",
    )
    if any(m in t for m in js_markers):
        return "blocked_js"
    return None


def fetch(engine, query, timeout=40):
    """Query one engine. Returns a fully-populated record dict.

    status is one of: 'ok', 'blocked_js', 'blocked_captcha', 'http_<code>',
    'timeout', 'error'. n_results is only meaningful when status == 'ok'; on
    any failure it is None so that empty (0) and failed are never conflated.
    """
    url = engine["url"].format(query=query)
    headers = {"User-Agent": random.choice(robin.USER_AGENTS)}
    rec = {
        "query": query,
        "engine": engine["name"],
        "ts": utcnow(),
        "status": None,
        "http_code": None,
        "latency_ms": None,
        "n_results": None,
        "results": [],
        "error": None,
    }
    t0 = time.monotonic()
    try:
        session = robin.get_tor_session()
        resp = session.get(url, headers=headers, timeout=timeout)
        rec["latency_ms"] = int((time.monotonic() - t0) * 1000)
        rec["http_code"] = resp.status_code
        if resp.status_code != 200:
            rec["status"] = "http_{}".format(resp.status_code)
            return rec

        soup = BeautifulSoup(resp.text, "html.parser")
        engine_host = (urlparse(url).hostname or "").lower()
        links = []
        for a in soup.find_all("a"):
            try:
                target = robin._extract_target_onion(a.get("href"), engine_host)
                if not target:
                    continue
                if (urlparse(target).hostname or "").lower() in robin._ENGINE_HOSTS:
                    continue
                title = a.get_text(strip=True)
                if not robin._is_useful_title(title):
                    continue
                links.append({"title": robin._trim_title(title), "link": target})
            except Exception:
                continue
        if not links:
            # Parse-first: only an empty page needs explaining.
            blocked = classify_block(resp.text)
            if blocked:
                rec["status"] = blocked
                return rec
        rec["status"] = "ok"
        rec["n_results"] = len(links)
        rec["results"] = links
        return rec
    except requests.exceptions.Timeout:
        rec["latency_ms"] = int((time.monotonic() - t0) * 1000)
        rec["status"] = "timeout"
        return rec
    except Exception as e:
        rec["latency_ms"] = int((time.monotonic() - t0) * 1000)
        rec["status"] = "error"
        rec["error"] = "{}: {}".format(type(e).__name__, e)[:300]
        return rec


def already_done(path):
    """Set of (query, engine) pairs already recorded, for resume-after-crash."""
    done = set()
    if not os.path.exists(path):
        return done
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
                done.add((r["query"], r["engine"]))
            except Exception:
                continue
    return done


def build_plan(reps, n_null, n_target, n_common):
    plan = []
    for rep in range(reps):
        conds = []
        conds += [("target", q) for q in TARGET[:n_target]]
        conds += [("common", q) for q in COMMON[:n_common]]
        conds += [("null", q) for q in make_null_queries(n_null)]
        random.shuffle(conds)  # defeat temporal/ordering confounds
        for qtype, q in conds:
            plan.append((rep, qtype, q))
    return plan


def main():
    ap = argparse.ArgumentParser(description="Onion search-engine measurement harness")
    ap.add_argument("--out", default=os.path.join(DATA_DIR, "results.jsonl"))
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--null", type=int, default=5)
    ap.add_argument("--target", type=int, default=5)
    ap.add_argument("--common", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=40)
    args = ap.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    done = already_done(args.out)
    exit_ip = tor_exit_ip()
    plan = build_plan(args.reps, args.null, args.target, args.common)

    # Expand plan into (query, engine) jobs, skipping any already recorded.
    jobs = []
    for rep, qtype, q in plan:
        for eng in robin.SEARCH_ENGINES:
            if (q, eng["name"]) in done:
                continue
            jobs.append((rep, qtype, q, eng))

    total = len(jobs)
    print("exit_ip={}  jobs={}  (skipped {} already done)".format(
        exit_ip, total, len(done)), flush=True)

    counts = {"ok": 0, "timeout": 0, "error": 0, "http": 0}
    n_done = 0
    fout = open(args.out, "a", encoding="utf-8")
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {}
            for rep, qtype, q, eng in jobs:
                fu = ex.submit(fetch, eng, q, args.timeout)
                futs[fu] = (rep, qtype, q, eng)
            for fu in as_completed(futs):
                rep, qtype, q, eng = futs[fu]
                rec = fu.result()
                rec["rep"] = rep
                rec["query_type"] = qtype
                rec["exit_ip"] = exit_ip
                fout.write(json.dumps(rec) + "\n")
                fout.flush()
                n_done += 1
                st = rec["status"] or "error"
                key = "http" if st.startswith("http") else st
                counts[key] = counts.get(key, 0) + 1
                if n_done % 10 == 0 or n_done == total:
                    print("  {}/{}  ok={} timeout={} http={} error={}".format(
                        n_done, total, counts["ok"], counts["timeout"],
                        counts["http"], counts["error"]), flush=True)
    finally:
        fout.close()
    print("DONE -> {}".format(args.out), flush=True)


if __name__ == "__main__":
    main()
