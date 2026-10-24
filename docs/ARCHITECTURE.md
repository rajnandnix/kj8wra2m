# Architecture

```
┌──────────────────────┐
│  Elexon BMRS API     │  public, no key
└──────────┬───────────┘
           │  python -m app.ingest   (one-off, or --refresh)
           ▼
┌──────────────────────┐
│  data/raw/*.json     │  raw responses, one file per request chunk, committed
│  data/app.db         │  SQLite: actuals, forecasts, meta, committed
└──────────┬───────────┘
           │  read-only at serve time
┌──────────▼───────────┐
│  FastAPI  /api/*     │  pandas analytics computed from the snapshot
└──────────┬───────────┘
           │  JSON
┌──────────▼───────────┐
│  React + Vite        │  Decision, Accuracy and Breakdown views
└──────────────────────┘
```

## Data flow

1. **Ingest.** `ingest.py` requests WINDFOR by `publishDateTime` in 7 day chunks (28 Dec 2025 to the end of 31 Jan 2026) and
   FUELHH wind by `settlementDate` for the delivery window. Each response is written to `data/raw/` before it is parsed, and
   a cached chunk is never re-fetched without `--refresh`. Every response is validated against the window requested, because
   the API silently ignores unknown parameters. Exact duplicate rows (chunk boundaries) are dropped and uniqueness is asserted.
   Forecasts published after the last decision day are not stored.
2. **Snapshot.** `data/app.db` holds `actuals`, `forecasts` and `meta`. The deployed app opens it read-only.
3. **Align.** `align.py` builds one row per hourly delivery interval (outer join against the complete expected index) with the
   vintage chosen by the cutoff rule, the hourly actual (mean of two half-hours), the error and the lead time. It does this for
   each configured cutoff.
4. **Metrics.** `metrics.py` is pure functions over that table: headline metrics, debiased metrics, breakdowns, the conditional
   procurement band, and the paired cutoff comparison with a day-block bootstrap.
5. **API.** `main.py` loads and aligns once per process, then serves five endpoints. Every response that depends on a cutoff
   echoes the cutoff rule that produced it.
6. **UI.** TanStack Query fetches the endpoints; Recharts draws the charts. No live external calls.

## API

| Endpoint | Returns |
|---|---|
| `GET /api/health` | Status, data window, row counts, build timestamp, cutoffs, demo days |
| `GET /api/forecast?deliveryDate=&cutoff=` | The decision-time forecast, outturn, the cutoff used and the procurement band |
| `GET /api/accuracy?from=&to=&cutoff=` | Headline metrics, histogram, daily table, error series, worst intervals |
| `GET /api/accuracy/breakdown?by=hour\|level\|day&basis=` | Grouped breakdowns |
| `GET /api/sensitivity` | The full metric set at every cutoff and each against the primary |

Interactive documentation is served at `/api/docs`.

## The no-lookahead rule

```
usable_forecast(t) = the row with startTime == t and the maximum publishTime
                     subject to publishTime + PUBLICATION_LAG <= decision_cutoff(D)
decision_cutoff(D) = (D - 1 day) at the gate-closure time, Europe/London, converted to UTC
```

`select_vintages` in `align.py` is the single implementation; the scalar `select_vintage` calls it. A test compares them
and a brute-force oracle.

## Deployment

On Vercel the front end is a static Vite build and `api/index.py` re-exports the FastAPI app as a Python function, with
`data/app.db` and `backend/app/**` included in the bundle (`vercel.json`). `/api/(.*)` is rewritten to the function. The same
code runs under Docker (an nginx container serving the build and proxying `/api` to a uvicorn container), but that path has not been
built or run in the authoring environment.
