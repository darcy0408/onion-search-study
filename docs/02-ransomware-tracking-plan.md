# Study 2 — Ransomware leak-site tracking

## Goal
A monitoring system that polls ransomware group leak sites, detects victim events,
archives raw evidence, and supports longitudinal analysis (group lifecycle, rebrand
detection, takedown efficacy).

## Why leak sites matter
Double-extortion crews publish victims on Tor "dedicated leak sites" (DLS) to pressure
payment. Most victims never disclose. **The DLS is usually the only public record a
breach happened.** It is the ground truth for the ransomware economy.

---

## Architecture
```
scheduler -> fetcher (Tor) -> parser (per group) -> normalizer -> SQLite
                                                                   |
                                              differ -> events -> alerter
                                                                   |
                                                                analysis
```

## Data model
```
group        { name, onion_addresses[], first_seen, last_seen, active,
               template_hash, btc_addresses[] }
snapshot     { group, onion, fetched_at, http_status, html_sha256, raw_path }
victim_post  { group, victim_name, victim_domain, discovered_at, published_at,
               countdown_expires, claimed_size, status, raw_html_hash }
event        { ts, type, group, victim, prev_snapshot, new_snapshot }
```
`status` in {countdown, published, removed}.

## The key mechanic: diffing
Every poll = a snapshot. The differ compares to the previous snapshot and emits:
- `new_victim`        — appeared on the site
- `victim_published`  — countdown expired, data posted
- `victim_removed`    — **disappeared before publication. Usually = paid.**
                        This is the most interesting measurable signal.
- `site_down` / `site_moved`

**Archive raw HTML + hash on every poll.** Parsers break constantly; you re-parse
from raw. Losing raw = losing the study.

---

## Phases

### Phase 0 — Prior art (day 1)
Read RansomWatch (`joshhighet/ransomwatch`) parser structure and `groups.json`.
Pull ransomware.live's API for a seed list. **Decide: extend RansomWatch vs. build
own.** Likely fork/extend — do not rediscover 100 onion addresses from scratch.

### Phase 1 — Fetcher (day 1-2)
- Tor session with circuit rotation (Robin's `get_tor_session()` is a start)
- Retry + exponential backoff — leak sites are DDoSed by rivals and LE constantly
- **Hard limits enforced in code:** max response size (e.g. 2 MB), text/html only,
  never follow download links. This is the ethics boundary made mechanical.
- Store raw + sha256 + timestamp

### Phase 2 — Parsers (day 2-5)
- One parser per group; every DLS has its own HTML
- Start with 3-5 high-volume groups (check ransomware.live for current leaders)
- **Design for failure:** parse error -> keep raw, flag for review, never drop the poll

### Phase 3 — Store + differ (day 5-6)
SQLite is fine at this scale. Differ emits typed events.

### Phase 4 — Monitoring loop (day 6-7)
Poll every 1-4 h. **Do not hammer.** Alerts to file / webhook.

### Phase 5 — Analysis (ongoing)
- Victim volume over time, by group
- Sector / geography (enrich victim_domain -> industry)
- Time-to-publish distribution — how long do victims really get?
- Paid-rate proxy via `victim_removed` events
- **Rebrand detection** (the clever part): cluster groups by
  `template_hash` similarity, BTC address reuse, onion descriptor patterns,
  HTTP header fingerprints. "New" group + old fingerprint = rebrand.
- **Takedown efficacy:** activity before/after LE ops (e.g. LockBit / Op Cronos).
  Did volume drop, or did affiliates migrate to other RaaS brands?

---

## Deliverables
- Scraper + per-group parsers
- SQLite DB with longitudinal snapshots
- Event log + alerting
- Rebrand-cluster analysis
- Report / dashboard

---

## Ethics / legal — THE HARD LINE
- **Metadata only.** Victim names, dates, claimed sizes.
- **NEVER download victim data dumps.** That is stolen PII. Possessing it is a legal
  and ethical problem regardless of research intent. The fetcher's size/type limits
  exist to make this impossible by accident.
- Think before republishing victim names — you would be amplifying the extortion.
  ransomware.live does; decide your own policy deliberately.
- Responsible disclosure: if you see a victim who clearly does not know yet, many
  researchers notify. Have a policy.

## OPSEC
- You are connecting to criminal infrastructure. **Dedicated VM, not your daily
  driver.** Some DLS fingerprint visitors.
- Treat every response as hostile. Parse in a sandbox. Never execute anything.
- Rate limit. Do not make yourself interesting.
- Legal posture: viewing a public DLS is generally fine; downloading dumps is not.
