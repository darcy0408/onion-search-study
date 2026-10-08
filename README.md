# Are onion search engines actually search engines?

A measurement study of the 16 Tor search engines queried by
[Robin](https://github.com/apurvsinghgautam/robin), an open-source dark web
OSINT tool. The question: do these engines return results that depend on the
query, or the same listings whatever you ask?

**Status: pilot.** Small n, nothing significance-tested. Read the limits in
[docs/PILOT-FINDINGS.md](docs/PILOT-FINDINGS.md) before quoting anything.

## Method

Each engine is sent three kinds of query:

| Condition | Example | What a real index should do |
|---|---|---|
| Null | a random 12-character string | return nothing |
| Common | `market`, `forum`, `news` | return a lot |
| Target | `SecureDrop`, `ProPublica` | return the known service |

The null condition is the control: anything an engine returns for a random
string cannot be a match. The harness records status, latency and error
separately from result count, so a failed request is never read as "zero
results".

## Pilot findings

- **Four engines behaved like real indexes.** Onionway, The Deep Searches, Tor66
  and Torland returned nothing for random strings and results for real terms.
- **Four refused to serve, silently.** Ahmia and Torgol require JavaScript; OSS
  and Torgle show CAPTCHA walls. All four answer HTTP 200, so Robin reports
  them as "no results" with no error.
- **Some engines return results for nonsense.** Amnesia, Excavator and Find Tor
  returned 10 to 33 results on average for random strings.
- **Reachability is a snapshot.** Find Tor failed 10 of 10 requests on one day
  and succeeded 20 of 20 the next.

## Files

| File | Purpose |
|---|---|
| `harness.py` | Queries every engine over Tor, one JSONL record per request |
| `analyze.py` | Reliability, precision by condition, null response rate, overlap |
| `patch_robin.py` | Patches Robin to say why a search returned nothing |
| `run-daily-rep.ps1` | Runs one repetition per day as a Windows scheduled task |
| `docs/01-study-design.md` | Study design and metrics, written before the runs |
| `docs/PILOT-FINDINGS.md` | Results and limits |
| `docs/02-ransomware-tracking-plan.md` | Plan for a second study. Not started. |

## Running it

The harness imports Robin's `search` module and uses its Tor session, so it runs
inside Robin's Docker container with this folder mounted at `/app/research`:

    docker exec robin python /app/research/harness.py --null 5 --target 5 --common 10
    docker exec robin python /app/research/analyze.py

## Why there is no data here

The raw output holds the title and `.onion` address of everything the engines
returned. Those listings include markets, fraud services and advertising for
child sexual abuse material. Publishing them would be publishing a directory,
so the raw data is not in this repository and `data/raw/` is gitignored.

## Ethics

- The harness records result titles and URLs only. It never fetches a result
  page and never follows a link.
- Queries are rate limited; small onion services have little capacity.
- An earlier ad-hoc run that searched for personal identifiers is not published.

## Acknowledgements

Built on [Robin](https://github.com/apurvsinghgautam/robin) by Apurv Singh
Gautam (MIT License). `patch_robin.py` contains short excerpts of Robin's source
as patch anchors.
