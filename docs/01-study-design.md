# Study 1 — Are onion search engines actually search engines?

## Research question
Do dark web search engines return **query-relevant** results, or **query-independent
sponsored placement**?

## Pilot finding (already collected, 2026-09-21)
5 unrelated queries x 16 engines -> **217 results, 0 containing the query term.**
`TorMart` and `Prime Market` appeared for an email-address query AND for an
unrelated drug query. (That ad-hoc run is not published; it queried personal
identifiers.)

## Hypothesis
H1: For most engines, result sets are statistically independent of the query.
H0: Result sets vary with query content (i.e. they genuinely index).

---

## Design

### Query conditions (independent variable)
| Condition | n | Purpose | Example |
|---|---|---|---|
| **Null** | 20 | Cannot match anything. Any result = noise. | `xj4qz9v2mkp7` (CSPRNG, 8-12 chars) |
| **Common** | 20 | High-frequency words, should match a lot | `market`, `forum`, `news` |
| **Target** | 20 | Known genuine onion presence | `SecureDrop`, `ProPublica`, `Ahmia` |
| **Rare-real** | 20 | Real but uncommon strings | specific group names, niche services |

Null is the key control: **a well-behaved search engine returns ZERO results for a
random 12-char string.** Anything it returns is definitionally not a match.

### Metrics (dependent variables)
1. **Precision@k** = results containing query term / k
2. **Null Response Rate (NRR)** = mean results returned for null queries. Ideal 0.
3. **Query Independence Index** = mean pairwise Jaccard J(A,B) between result sets of
   *unrelated* queries. J -> 1 means the engine ignores the query entirely.
4. **Sponsored Core** = set of onions appearing in >50% of ALL result sets regardless
   of query. Size and membership of this set is a headline finding.
5. **Inter-engine overlap matrix** = J between engines for the same query.
   Reveals whether 16 engines = 16 indexes or 1 shared ad pool.
6. **Liveness rate** = fraction of returned .onion addresses that actually resolve.

### Controls / rigor
- **Randomize query order** — defeats temporal confounds from ad rotation.
- **3 repetitions per query at different times of day** — measures ad rotation and
  result stability.
- **Distinguish failure from emptiness.** An HTTP timeout is NOT "zero results".
  Record `status`, `latency_ms`, `error` separately. This is the single easiest way
  to ruin the study.
- **Record the Tor exit** per request — rules out exit-specific behaviour.
- **Pre-register** metrics in this file before the full run. No moving the goalposts.

### Statistics
- NRR: mean +/- binomial CI per engine.
- Per engine, compare Precision(null) vs Precision(target). **No significant
  difference = the engine does not search.** That is the money test.
- FDR correction (Benjamini-Hochberg) across the 16 engines.

---

## Phases

### Phase 0 — Harness (day 1)
Reuse `fetch_search_results(endpoint, query)` from Robin's `search.py` — it already
does per-engine querying over Tor.

Build `harness.py` emitting **JSONL** (append-only, resumable after crash):
```json
{"run_id","query","query_type","engine","ts","status","latency_ms",
 "n_results","results":[{"title","link"}],"error","exit_ip"}
```

### Phase 1 — Pilot (day 1-2)
5 null + 5 target x 16 engines = 160 requests.
Validate harness, measure per-request latency, extrapolate full-study wall clock.
Sanity check: does **Ahmia** outperform the rest? (Expected: yes — real index,
clearnet frontend, active moderation.)

### Phase 2 — Full run (day 2-4)
80 queries x 16 engines x 3 reps = **3,840 requests**.
At ~10s/req with parallelism 4 -> ~3h per rep. Run overnight, resumable.

### Phase 3 — Liveness (day 4)
Dedupe every returned .onion, attempt a Tor connection to each, record reachability.
**HEAD/connect only — do not fetch page bodies.** (See Ethics.)

### Phase 4 — Analysis (day 5)
All six metrics, per-engine scorecard, overlap heatmap, significance tests.

### Phase 5 — Output
- **Practical:** ranked engine list -> patch Robin's `SEARCH_ENGINES` to drop the
  ad farms. The research directly improves the tool.
- **Publishable:** writeup / lightning talk.

---

## Deliverables
- `harness.py`, `analyze.py`
- `results.jsonl` (raw, archived, not published; see the README)
- Per-engine scorecard + overlap heatmap
- `FINDINGS.md`
- Patch to Robin's engine list

---

## Threats to validity
| Threat | Mitigation |
|---|---|
| Rate limiting confounded with "no results" | Record HTTP status separately; retry w/ backoff |
| Tor circuit variance | 3 reps; record exit IP; retry policy |
| Ad rotation over time | 3 reps at different times of day |
| Query terms accidentally matching ad copy | Null queries are the clean control |
| Engine death mid-study | Timestamp everything; report per-engine uptime |

---

## Ethics / legal
- Legal: querying public search engines and recording **metadata**.
- **Record titles + URLs ONLY. Never fetch result page bodies.** The pilot surfaced
  CSAM advertising in result titles; fetching those pages is both an ethical and a
  legal hazard. Enforce in code, not policy.
- Rate limit politely. Small onion services have little capacity.
- Never follow links.
