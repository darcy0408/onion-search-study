#!/usr/bin/env python3
"""Patch Robin so it reports WHY a search returned nothing.

Robin returns [] for a timeout, an HTTP error, a CAPTCHA wall and a genuinely
empty result set alike. So "nothing matched your search" and "the search could
not be completed" look identical in the UI. Those are different facts, and the
difference matters: the second one is not evidence of absence.

Applies two changes:
  1. search.py  -- appends detailed fetch + a results list carrying per-engine
                   status. Appending overrides the earlier definitions (Python
                   binds the last one), which avoids fragile string surgery.
  2. ui.py      -- replaces the single "no results" message with three cases:
                   all engines failed / partial coverage / genuine no-match.

Idempotent: re-running is a no-op. Re-apply after any `docker rm` + `run`,
since the container filesystem is ephemeral:
    docker exec robin python //app/research/patch_robin.py
"""
import io
import os
import sys

MARKER = "# --- robin-reliability-patch ---"

SEARCH_PATCH = '''

# --- robin-reliability-patch ---
# Appended deliberately: these override the earlier definitions above, so the
# original source is left byte-for-byte intact and the patch stays reversible.

def _classify_unavailable(text):
    """Explain a 200-OK page that returned no parseable results.

    Only consulted when parsing already yielded nothing. A page that yields
    results is by definition available, so checking markers on every page
    produces false positives (some engines' own copy mentions JavaScript
    while serving perfectly good results).
    """
    t = (text or "").lower()
    captcha_markers = (
        "solve this captcha", "solve the following", "solve this simple",
        "required to solve", "- captcha", "\\u2013 captcha",
    )
    if any(m in t for m in captcha_markers):
        return "captcha_wall"
    js_markers = (
        "non-javascript version", "javascript is disabled in your browser",
        "please enable javascript", "search feature will not work",
    )
    if any(m in t for m in js_markers):
        return "requires_javascript"
    return None


def fetch_search_results_detailed(endpoint, query):
    """Query one engine, returning both its results AND what happened.

    status: 'ok' | 'timeout' | 'http_<code>' | 'captcha_wall'
            | 'requires_javascript' | 'error'
    """
    url = endpoint.format(query=query)
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    out = {"status": "ok", "http_code": None, "links": [], "error": None}
    try:
        session = get_tor_session()
        response = session.get(url, headers=headers, timeout=40)
        out["http_code"] = response.status_code
        if response.status_code != 200:
            out["status"] = "http_{}".format(response.status_code)
            return out

        soup = BeautifulSoup(response.text, "html.parser")
        engine_host = (urlparse(url).hostname or "").lower()
        links = []
        for a in soup.find_all("a"):
            try:
                target = _extract_target_onion(a.get("href"), engine_host)
                if not target:
                    continue
                if (urlparse(target).hostname or "").lower() in _ENGINE_HOSTS:
                    continue
                title = a.get_text(strip=True)
                if not _is_useful_title(title):
                    continue
                links.append({"title": _trim_title(title), "link": target})
            except Exception:
                continue

        if not links:
            reason = _classify_unavailable(response.text)
            if reason:
                out["status"] = reason
                return out
        out["links"] = links
        return out
    except requests.exceptions.Timeout:
        out["status"] = "timeout"
        return out
    except Exception as e:
        out["status"] = "error"
        out["error"] = "{}: {}".format(type(e).__name__, e)[:200]
        return out


class SearchResults(list):
    """Result list that also carries per-engine status.

    Subclasses list so every existing caller keeps working unchanged.
    """

    def __init__(self, items=(), diagnostics=None):
        super().__init__(items)
        self.diagnostics = dict(diagnostics or {})

    @property
    def engines_ok(self):
        return sorted(e for e, s in self.diagnostics.items() if s == "ok")

    @property
    def engines_failed(self):
        return {e: s for e, s in self.diagnostics.items() if s != "ok"}


def get_search_results(refined_query, max_workers=5):
    results = []
    diagnostics = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_search_results_detailed, eng["url"], refined_query):
                eng["name"]
            for eng in SEARCH_ENGINES
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                out = future.result()
            except Exception as e:
                diagnostics[name] = "error"
                continue
            diagnostics[name] = out.get("status", "error")
            results.extend(out.get("links") or [])

    seen_links = set()
    unique_results = []
    for res in results:
        link = res.get("link") or ""
        try:
            clean_link = _dedup_key(link)
        except Exception:
            clean_link = link.rstrip("/")
        if clean_link not in seen_links:
            seen_links.add(clean_link)
            unique_results.append(res)

    return SearchResults(unique_results, diagnostics)
'''

UI_OLD = '''    if not st.session_state.results:
        _render_no_results(
            "No dark web results came back for this query.",
            [
                "- Try broader or differently worded search terms.",
                "- Run **Check Search Engines** in the sidebar; onion engines have irregular uptime.",
                "- Confirm Tor is running and reachable on `socks5h://127.0.0.1:9050`.",
            ],
        )'''

UI_NEW = '''    if not st.session_state.results:
        # --- robin-reliability-patch ---
        # Distinguish "nothing matched" from "the search could not be completed".
        _diag = getattr(st.session_state.results, "diagnostics", {}) or {}
        _failed = {e: s for e, s in _diag.items() if s != "ok"}
        _ok = [e for e, s in _diag.items() if s == "ok"]
        if _diag and not _ok:
            _render_no_results(
                f"The search could not be completed \\u2014 none of the {len(_failed)} engines returned a usable response.",
                [f"- {e}: {s}" for e, s in sorted(_failed.items())][:8]
                + ["- **This is not evidence the term is absent from the dark web.**",
                   "- Confirm Tor is running and reachable on `socks5h://127.0.0.1:9050`."],
            )
        elif _failed:
            _render_no_results(
                f"No matches from the {len(_ok)} engines that responded. {len(_failed)} could not be reached.",
                [f"- unreachable: {e} ({s})" for e, s in sorted(_failed.items())][:8]
                + ["- Coverage was partial, so this is weak evidence of absence.",
                   "- Try broader or differently worded search terms."],
            )
        else:
            _render_no_results(
                f"No matches. All {len(_ok)} engines responded, none had results for this query.",
                ["- Try broader or differently worded search terms.",
                 "- These engines index only part of the onion web, so absence here "
                 "is not absence from the dark web."],
            )'''


def patch_file(path, check, apply_fn):
    with io.open(path, encoding="utf-8") as f:
        src = f.read()
    if check in src:
        print("  SKIP {} (already patched)".format(path))
        return False
    new = apply_fn(src)
    if new is None:
        print("  FAIL {} (anchor text not found)".format(path))
        return False
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(new)
    print("  OK   {}".format(path))
    return True


def main():
    print("patching Robin...")
    patch_file("/app/search.py", MARKER, lambda s: s + SEARCH_PATCH)
    patch_file("/app/ui.py", MARKER,
               lambda s: s.replace(UI_OLD, UI_NEW) if UI_OLD in s else None)
    print("done. restart Streamlit for ui.py changes to take effect.")


if __name__ == "__main__":
    main()
