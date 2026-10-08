# Pilot findings — Study 1

**Run:** v3, 2026-09-22. 5 null + 5 target queries x 16 engines = 160 requests.
**Data:** not published (see the README). `results.jsonl` is the run reported
here; v1 and v2 were earlier runs with the instrument faults described below.
**Status:** pilot-strength. Not significance-tested. n is small; treat as directional.

---

## Headline: a five-tier taxonomy

| Tier | n | Engines |
|---|---|---|
| **RESPONDED, MATCHED** | 4 | Onionway (34.5%), Deep Searches (34.4%), Tor66 (15.5%), Torland (100%*) |
| **RESPONDED, MIXED** | 3 | Amnesia (13 results for nonsense / 12.6%), Excavator (10 / 15.3%), TorNet (2 / 20.0%) |
| **RESPONDED, UNVARYING** | 1 | OnionLand (identical list every query; same match rate for nonsense and real terms) |
| **REFUSED TO SERVE** | 4 | Ahmia (needs JS), Torgol (needs JS), OSS (CAPTCHA), Torgle (CAPTCHA) |
| **NO USABLE RESPONSE** | 4 | Anima, Find Tor, Kaizer, Tornado |

\* Torland's 100% is computed over a single query with results. Expect regression
at full n. Do not quote it.

---

## LIMITS — what this pilot does NOT establish

Read this before quoting anything above.

1. **"No usable response" does not mean the engine is dead.** We saw failures from
   one machine, through Tor, over a single short window. That is consistent with
   the engine being offline, but equally with rate-limiting, blocking our exit
   node, transient circuit failure, or the service having moved. We did not test
   from a second vantage point or at a second time. The honest claim is
   *"Robin could not reach it during our runs."*

2. **Recurring links are not proven to be paid advertising.** We measured that
   certain onions reappear across unrelated queries. We never established that
   anyone paid for that placement. They could equally be default listings, a
   curated directory's fixed entries, genuinely popular destinations, or the
   engine's own affiliates. The measurable fact is *recurrence*, not *payment*.
   Earlier drafts of this file called this a "sponsored core" -- that was an
   inference, not a measurement.

3. **Finding no match for a person's details does not mean the data is absent
   from the dark web.** These engines index a small and unknown fraction of onion
   services. Breach-dump sites and private forums are largely not indexed at all.
   A null result here constrains almost nothing.

4. **Match rate does not distinguish a crawler from a hand-curated directory.**
   A maintained list of well-known services would score just as well on
   "SecureDrop" and "ProPublica" as a real crawler. The common-word condition is
   *additional evidence* on this question, not a decisive test.

5. **Pilot n is small** (10 queries per engine) and nothing is significance-tested.

**CLEAN INDEX** = returned *zero* results for random 12-char strings (NRR 0.0)
while still hitting on real targets. This is correct search-engine behaviour.

**HYBRID** = returns a sponsored floor regardless of query (NRR 10-13 for Amnesia
and Excavator) but target precision still exceeds null precision. Roughly half
their output is query-independent (Jaccard 0.47-0.68).

---

## Finding 1 — half of Robin's engine list contributes nothing

**8 of 16 engines return zero usable results, silently.**

The 4 BLOCKED engines all return **HTTP 200**, which is why nothing ever surfaces
an error. Robin's `fetch_search_results()` returns `[]` for non-200, timeout, and
exception alike, so a JS shell and a dead engine are indistinguishable from
"no results for your query".

- **Ahmia**: *"Unfortunately we have not deployd non-JavaScript version of Ahmia yet."*
  Ahmia is the most credible index in the list (moderated, clearnet frontend).
  Robin scrapes with requests+BeautifulSoup, executes no JS, and gets an empty
  shell. **Every Robin investigation has received zero Ahmia results, silently.**
- **Torgol**: *"JavaScript is disabled in your browser. Search feature will not work."*
- **OSS** and **Torgle**: CAPTCHA walls ("solve this math problem", DDoS mitigation).

### Practical patch
Dropping the 8 non-contributing engines from `SEARCH_ENGINES` costs zero results
and should roughly halve wall-clock per investigation. Ahmia is worth recovering
separately via its clearnet frontend (ahmia.fi), which serves without JS.

---

## Finding 2 — "it's all sponsored spam" was too strong

An earlier ad-hoc run (5 identifier queries, 217 results, 0 term matches) suggested
these engines were pure ad delivery. The pilot refutes that as a blanket claim.

Those queries were email addresses and a personal name — strings with genuinely
**zero** onion presence. Zero matches was the *correct* answer, not evidence of
engine failure. What was visible was the sponsored floor showing through in the
absence of real results.

Against targets that genuinely exist, 4 engines return relevant results with a
clean null baseline. The honest finding is a **tiering**, not a dismissal.

---

## Instrument corrections (both would have survived into a writeup)

**v1 -> v2.** Four engines scored as "indexes nothing" were actually refusing to
serve. Added block classification. Without it the headline would have read
"Ahmia indexes nothing", which is flatly false.

**v2 -> v3.** The classifier matched marker strings *anywhere* in the document.
Excavator serves real results on a page whose own copy reads "learn how JavaScript
is disabled" — and was discarded as blocked. Produced a plausible-looking 9 ok /
1 blocked rather than an obvious error.
Fix was a rule, not a regex: **parse first; a page that yields results is by
definition not blocked.** Markers now only explain an already-empty page.

**Analyzer verdict logic.** Null precision is `None` when an engine returns zero
results for random strings. The original logic read that as missing data and
labelled the three *best* engines "insufficient results" — inverting the ranking.
Undefined-because-empty is the ideal outcome and must rank above a hybrid.

**Latency.** `time.time()` is not monotonic; one v1 reading was negative under NTP
adjustment. Now `time.monotonic()`.

---

## v4 — three-condition run (320 requests, 2026-09-23)

### The important result: "no usable response" was wrong about Find Tor

Find Tor failed **10/10** requests in v3 and was filed under "no usable response".
In v4 it succeeded **20/20** and returned results for every condition.

Nothing about the engine changed that we know of. It was simply unreachable from
this machine during one window and reachable during another. This is direct
evidence for limit #1 above, produced within a day of writing it. **Any
single-session reachability result should be treated as a snapshot, not a
property of the engine.** The full study needs repeated runs across days and
ideally a second vantage point before making any claim about availability.

Kaizer also changed failure mode (v3: 10 errors; v4: 16 timeouts + 4 errors) --
consistent with an overloaded or very slow service rather than an absent one.

By contrast, the four REFUSED-TO-SERVE engines were **identical across all runs**
(Ahmia + Torgol require JavaScript; OSS + Torgle show CAPTCHA walls). That
consistency is what makes those the trustworthy findings so far.

### Average results returned, by term type

| Engine | Nonsense | Common words | Known-real names |
|---|---|---|---|
| Onionway | **0.0** | 22.0 | 22.0 |
| The Deep Searches | **0.0** | 19.0 | 17.6 |
| Tor66 | **0.0** | 45.0 | 34.8 |
| Torland | **0.0** | 17.3 | 0.8 |
| OnionLand | 2.0 | 2.0 | 2.0 |
| TorNet | 2.0 | 16.2 | 4.0 |
| Excavator | 10.0 | 19.7 | 19.6 |
| Amnesia | 13.0 | 95.1 | 17.4 |
| Find Tor | 33.0 | 69.8 | 35.0 |

**Confound -- read before interpreting the match rates.** Word frequency is not
controlled between conditions. "market" and "forum" appear in far more onion page
titles than "ProPublica" does. So a higher match rate on common words mostly
reflects how common the word is, NOT how good the index is. Match rates are
therefore **not comparable across conditions**. Only two things here are safe to
read:

- the **nonsense column**, where the correct value is 0 regardless of word choice;
- **how much an engine's output volume varies** between wildly different queries.

On that second reading, OnionLand returns exactly 2.0 results for nonsense, common
words and real names alike -- its output barely responds to the query at all.
Amnesia varies a lot (13 / 95 / 17).

**Torland is an open question, not a finding.** It returns 17.3 results for common
words but 0.8 for specific service names. That pattern would fit a category-style
directory, but it would also fit a crawler with thin coverage, and n is small.
Recorded as a hypothesis to test, not a conclusion.

---

## Next
1. Enable the `common` condition (20 high-frequency words, currently `--common 0`).
   Sits between null and target; should separate "broad index" from "curated directory".
2. Full run: 80 queries x 16 engines x 3 reps = 3,840 requests.
   ~8-10 min per 160 requests observed -> ~3-4 h per rep. Overnight, resumable.
3. Phase 3 liveness sweep over every returned .onion.
4. Significance testing + FDR correction across engines.
