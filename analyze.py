#!/usr/bin/env python3
"""Study 1 analysis: compute the six metrics over harness output.

Reads results.jsonl and reports, per engine:
  1. Reliability      -- ok / timeout / http / error breakdown
  2. Precision@k      -- fraction of results containing the query term
  3. NRR              -- mean results returned for NULL queries (ideal: 0)
  4. Query Independence -- mean pairwise Jaccard across UNRELATED queries
  5. Recurring hosts  -- onions reappearing across unrelated queries.
                         NOT evidence of paid placement: the onion web is
                         itself ~82% replicated mirrors (Snorkeling, 2025),
                         which explains recurrence without any ad hypothesis.
  6. Inter-engine overlap matrix

The money test is #2 vs #3: an engine whose null-query precision matches its
target-query precision is not searching, it is serving a fixed list.

Only records with status == 'ok' feed the result-based metrics; failures are
reported separately so "engine down" is never read as "engine returned nothing".
"""
import argparse
import json
import os
from collections import defaultdict
from itertools import combinations
from urllib.parse import urlparse


def load(path):
    """Load one JSONL file, or every rep-*.jsonl in a directory."""
    import glob as _glob
    paths = []
    if os.path.isdir(path):
        paths = sorted(_glob.glob(os.path.join(path, "rep-*.jsonl")))
        extra = os.path.join(path, "results.jsonl")
        if os.path.exists(extra):
            paths.append(extra)
    else:
        paths = [path]
    recs = []
    for p in paths:
        src = os.path.basename(p)
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    r["_src"] = src
                    r["_day"] = (r.get("ts") or "")[:10] or src
                    recs.append(r)
                except Exception:
                    continue
    if len(paths) > 1:
        print("loaded {} files: {}".format(len(paths), ", ".join(os.path.basename(p) for p in paths)))
    return recs


def reachability_by_day(recs):
    """Per-engine reachability across days.

    Reported as a matrix rather than an average because averaging hides the
    thing that matters: Find Tor was 0% one day and 100% the next. A single
    pooled number would have shown ~50% and implied a flaky-but-present
    service, which is a different and less honest claim than 'it varies'.
    """
    days = sorted({r["_day"] for r in recs})
    if len(days) < 2:
        return
    engines = sorted({r["engine"] for r in recs})
    print("\n--- REACHABILITY BY DAY (% of requests returning results) ---")
    print("  Blank = no data. Watch for engines that flip between days.")
    hdr = "{:<20}".format("engine") + "".join("{:>7}".format(d[5:]) for d in days)
    print(hdr)
    for e in engines:
        cells = ""
        vals = []
        for d in days:
            rs = [r for r in recs if r["engine"] == e and r["_day"] == d]
            if not rs:
                cells += "{:>7}".format("-")
                continue
            ok = sum(1 for r in rs if r["status"] == "ok")
            v = 100.0 * ok / len(rs)
            vals.append(v)
            cells += "{:>7}".format("{:.0f}%".format(v))
        flag = ""
        if len(vals) > 1 and (max(vals) - min(vals)) >= 50:
            flag = "  <-- VARIES"
        print("{:<20}{}{}".format(e[:20], cells, flag))


def host_of(url):
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def term_hit(query, result):
    """Does this result actually reference the query term?"""
    q = query.lower().strip()
    if not q:
        return False
    blob = (result.get("title", "") + " " + result.get("link", "")).lower()
    return q in blob


def jaccard(a, b):
    if not a and not b:
        return None
    u = len(a | b)
    return len(a & b) / u if u else None


def pct(x):
    return "n/a" if x is None else "{:.1f}%".format(100 * x)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "raw"))
    ap.add_argument("--core-threshold", type=float, default=0.5)
    args = ap.parse_args()

    recs = load(args.data)
    if not recs:
        print("no records at {}".format(args.data))
        return

    engines = sorted({r["engine"] for r in recs})
    qtypes = sorted({r.get("query_type", "?") for r in recs})
    print("=" * 78)
    print("records={}  engines={}  query_types={}".format(
        len(recs), len(engines), ",".join(qtypes)))
    print("=" * 78)

    # ---------- 1. reliability ----------
    print("\n--- 1. RELIABILITY (all records) ---")
    print("{:<20} {:>4} {:>4} {:>5} {:>4} {:>8} {:>7}".format(
        "engine", "ok", "t/o", "http", "err", "blocked", "ok%"))
    rel = {}
    blocked_kind = {}
    for e in engines:
        rs = [r for r in recs if r["engine"] == e]
        ok = sum(1 for r in rs if r["status"] == "ok")
        to = sum(1 for r in rs if r["status"] == "timeout")
        ht = sum(1 for r in rs if (r["status"] or "").startswith("http"))
        er = sum(1 for r in rs if r["status"] == "error")
        bl = [r["status"] for r in rs if (r["status"] or "").startswith("blocked")]
        rel[e] = ok / len(rs) if rs else 0
        if bl:
            blocked_kind[e] = max(set(bl), key=bl.count).replace("blocked_", "")
        print("{:<20} {:>4} {:>4} {:>5} {:>4} {:>8} {:>7}".format(
            e[:20], ok, to, ht, er,
            "{} {}".format(len(bl), blocked_kind.get(e, "")) if bl else "-",
            pct(rel[e])))
    if blocked_kind:
        print("\n  BLOCKED = HTTP 200 but refusing to serve results (JS shell or")
        print("  CAPTCHA wall). These engines are unreachable to any non-JS")
        print("  scraper -- a different claim from 'indexes nothing'.")

    reachability_by_day(recs)

    # ---------- 2 & 3. precision by condition, NRR ----------
    print("\n--- 2+3. PRECISION BY CONDITION  (the money test) ---")
    print("{:<20} {:>10} {:>10} {:>10} {:>10}".format(
        "engine", "null n", "NULL prec", "TGT prec", "NRR"))
    verdicts = {}
    for e in engines:
        ok = [r for r in recs if r["engine"] == e and r["status"] == "ok"]
        row = {}
        for qt in ("null", "target", "common"):
            sub = [r for r in ok if r.get("query_type") == qt]
            tot = sum(len(r["results"]) for r in sub)
            hit = sum(1 for r in sub for x in r["results"] if term_hit(r["query"], x))
            row[qt] = (hit / tot) if tot else None
            row[qt + "_n"] = tot
        nulls = [r for r in ok if r.get("query_type") == "null"]
        nrr = (sum(r["n_results"] for r in nulls) / len(nulls)) if nulls else None
        verdicts[e] = (row.get("null"), row.get("target"), nrr)
        print("{:<20} {:>10} {:>10} {:>10} {:>10}".format(
            e[:20], row.get("null_n", 0), pct(row.get("null")),
            pct(row.get("target")),
            "n/a" if nrr is None else "{:.1f}".format(nrr)))

    print("\n  NRR = mean results returned for a random 12-char string.")
    print("  A real index returns 0. Anything above 0 is query-independent output.")

    # ---------- 4. query independence ----------
    print("\n--- 4. QUERY INDEPENDENCE (mean pairwise Jaccard, unrelated queries) ---")
    print("  J->1.0 means the engine returns the same set regardless of query.")
    print("{:<20} {:>12} {:>8}".format("engine", "mean J", "pairs"))
    for e in engines:
        ok = [r for r in recs if r["engine"] == e and r["status"] == "ok" and r["results"]]
        sets = {}
        for r in ok:
            sets.setdefault(r["query"], set()).update(host_of(x["link"]) for x in r["results"])
        js = []
        for a, b in combinations(sorted(sets), 2):
            j = jaccard(sets[a], sets[b])
            if j is not None:
                js.append(j)
        mean_j = sum(js) / len(js) if js else None
        print("{:<20} {:>12} {:>8}".format(
            e[:20], "n/a" if mean_j is None else "{:.3f}".format(mean_j), len(js)))

    # ---------- 5. sponsored core ----------
    print("\n--- 5. SPONSORED CORE (hosts appearing across most result sets) ---")
    setcount = 0
    host_sets = defaultdict(int)
    for r in recs:
        if r["status"] != "ok" or not r["results"]:
            continue
        setcount += 1
        for h in {host_of(x["link"]) for x in r["results"]}:
            if h:
                host_sets[h] += 1
    core = [(h, c) for h, c in host_sets.items()
            if setcount and c / setcount >= args.core_threshold]
    core.sort(key=lambda t: -t[1])
    print("  {} non-empty result sets; {} hosts appear in >={:.0f}% of them".format(
        setcount, len(core), 100 * args.core_threshold))
    for h, c in core[:20]:
        print("    {:>6}  {}".format("{:.0f}%".format(100 * c / setcount), h[:64]))
    if not core:
        top = sorted(host_sets.items(), key=lambda t: -t[1])[:10]
        print("  (none above threshold; most frequent hosts:)")
        for h, c in top:
            print("    {:>6}  {}".format(
                "{:.0f}%".format(100 * c / setcount) if setcount else "?", h[:64]))

    # ---------- 6. inter-engine overlap ----------
    print("\n--- 6. INTER-ENGINE OVERLAP (mean J for the same query) ---")
    by_q = defaultdict(dict)
    for r in recs:
        if r["status"] != "ok" or not r["results"]:
            continue
        by_q[r["query"]].setdefault(r["engine"], set()).update(
            host_of(x["link"]) for x in r["results"])
    pair_j = defaultdict(list)
    for q, per_eng in by_q.items():
        for a, b in combinations(sorted(per_eng), 2):
            j = jaccard(per_eng[a], per_eng[b])
            if j is not None:
                pair_j[(a, b)].append(j)
    ranked = sorted(((sum(v) / len(v), a, b, len(v)) for (a, b), v in pair_j.items()),
                    reverse=True)
    print("  top overlapping engine pairs (shared ad pool candidates):")
    for j, a, b, n in ranked[:12]:
        print("    J={:.3f}  n={:<3}  {}  <->  {}".format(j, n, a[:22], b[:22]))

    # ---------- verdict ----------
    print("\n" + "=" * 78)
    print("VERDICT (pilot-strength, not significance-tested)")
    print("=" * 78)
    for e in engines:
        nl, tg, nrr = verdicts[e]
        # NOTE: null precision is None when the engine returned ZERO results for
        # random strings. That is not missing data -- it is the ideal outcome
        # (nothing to be imprecise about) and must rank ABOVE a hybrid engine
        # that returns a sponsored floor. Treating it as "insufficient" inverted
        # the ranking and hid the three best-behaved engines.
        clean_null = (nrr == 0)
        if e in blocked_kind:
            v = "BLOCKED ({}) -- unusable by any non-JS scraper".format(blocked_kind[e])
        elif rel.get(e, 0) == 0:
            v = "DEAD (all requests failed)"
        elif clean_null and tg:
            v = "CLEAN INDEX -- 0 results for random strings, {} target precision".format(pct(tg))
        elif clean_null and not tg:
            v = "quiet -- 0 for random strings, but no target hits either"
        elif nrr and tg is not None and nl is not None and tg <= nl + 0.05:
            v = "NOT SEARCHING (NRR={:.1f}, target == null precision)".format(nrr)
        elif nrr and tg is not None and nl is not None and tg > nl + 0.05:
            v = "HYBRID -- sponsored floor (NRR={:.1f}) + real index ({} target)".format(nrr, pct(tg))
        elif nrr:
            v = "NOT SEARCHING (NRR={:.1f}, no target signal)".format(nrr)
        else:
            v = "insufficient results"
        print("  {:<22} {}".format(e[:22], v))


if __name__ == "__main__":
    main()
