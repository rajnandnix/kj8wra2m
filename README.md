# GB day-ahead wind forecast risk

A utility buys electricity on the GB day-ahead market on D-1 for delivery on D. Wind is free but uncertain, and every
megawatt the forecast gets wrong has to be covered later at higher cost. This app shows the wind forecast that was
actually available at each day-ahead gate closure (never a later one), measures how wrong it has been over January 2026
decisions, and turns that error history into a band to size thermal cover around the forecast.

## Live demo

**https://gb-wind-risk-x7q2.vercel.app** (React front end plus a Python function on Vercel; API docs at `/api/docs`).

## Screenshots

| Decision view | Accuracy view |
|---|---|
| ![Decision view: forecast at the cutoff, outturn and the procurement band](docs/screenshots/decision.png) | ![Accuracy view: the lead finding and headline metrics](docs/screenshots/accuracy.png) |

![Breakdown view: error by hour and by generation level](docs/screenshots/breakdown.png)

## Key findings

All figures are for the 31 delivery days 2 Jan to 1 Feb 2026 (744 hourly intervals, 100% coverage) at the primary
09:20 cutoff (EPEX SPOT GB 60 minute auction gate), measured against FUELHH metered wind. Error is forecast minus actual.

- **The lead finding.** MAE is **2,039 MW**, and the forecast ran **+1,748 MW high** on average. Remove that systematic
  offset and MAE falls to **1,376 MW**. These are two measured figures, not an additive split. **A standing correction
  would cut the typical miss by about a third** (an in-sample estimate from one month).
- **The offset is scope, not a bug.** WINDFOR covers wind that FUELHH leaves out, chiefly embedded wind. Checked against
  independent sources (NESO's embedded-wind estimate and Elexon's AGWS national wind), the day-ahead MAE against full-fleet
  outturn is 1,330 to 1,518 MW (nMAE 10 to 11%) and the bias is slightly negative (about −0.4 to −0.7 GW).
  Details: [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md) section 8.2.
- **Later gate, modest gain.** At the 15:30 gate MAE is 6.6% lower (1,904 MW), but the 95% interval (−14.8% to +0.4%)
  reaches zero, so one month supports a directional case only. The 09:50 gate is no different from 09:20.
- **Procurement band.** For each hour, realised wind is expected between forecast minus P90 and forecast minus P10 of the
  error for hours with a similar forecast level. P90 thermal cover is about 2.2 GW below 6 GW of forecast and 4.7 GW at 14 GW
  and above. In-sample coverage is 78 to 80% in every level bucket (a single global band ranged 69 to 89%). This is
  in-sample; one month cannot support out-of-sample validation.

## Architecture

```
┌──────────────────────┐
│  Elexon BMRS API     │  (public, keyless)
└──────────┬───────────┘
           │  one-off ingestion: python -m app.ingest
           ▼
┌──────────────────────┐
│  data/raw/*.json     │  cached raw responses, committed
│  data/app.db         │  SQLite built from raw, committed
└──────────┬───────────┘
           │
┌──────────▼───────────┐
│  FastAPI backend     │  analytics computed from the snapshot, read-only
│  /api/*              │
└──────────┬───────────┘
           │  JSON
┌──────────▼───────────┐
│  React + Vite front  │  three views
└──────────────────────┘
```

The analysis window is fixed history, so the data is ingested once and **committed as a snapshot**: the deployed app
reads `data/app.db` read-only and makes no live call to Elexon. The numbers are byte-identical everywhere and cannot break
because a data provider is slow. `python -m app.ingest --refresh` re-fetches and rebuilds, so the live path exists but is not
on the request path. More in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Directory and file guide

| Path | Purpose |
|---|---|
| `backend/app/config.py` | Single source of truth: dates, decision cutoffs, publication lag, demo days, URLs, paths |
| `backend/app/ingest.py` | Fetch Elexon, cache raw responses to `data/raw/`, build `data/app.db` |
| `backend/app/storage.py` | Read-only SQLite access |
| `backend/app/align.py` | Forecast vintage selection (the no-lookahead rule) and hourly alignment |
| `backend/app/metrics.py` | MAE, RMSE, bias, percentiles, breakdowns, conditional band, cutoff comparison (pure functions) |
| `backend/app/schemas.py` | Typed API response models |
| `backend/app/main.py` | FastAPI app and routes |
| `backend/tests/` | `test_align.py` (no-lookahead), `test_metrics.py` (hand-computed formulas), `test_api.py` (contract) |
| `backend/requirements-dev.txt`, `backend/pyproject.toml` | Test and lint dependencies; tool configuration |
| `frontend/src/` | React app: `pages/` (three views), `components/` (panels and charts), `hooks/`, `lib/` |
| `frontend/Dockerfile`, `frontend/nginx.conf.template` | Static build served by nginx, proxying `/api` |
| `backend/Dockerfile`, `docker-compose.yml` | Backend image and the two-service compose file |
| `api/index.py`, `vercel.json` | Vercel serverless entry and routing |
| `requirements.txt` | Runtime dependencies for the API (Docker image and Vercel) |
| `data/raw/` | Cached raw Elexon responses (committed) |
| `data/app.db` | SQLite snapshot built from `data/raw/` (committed) |
| `docs/ASSUMPTIONS.md` | Every verified API fact, assumption and validation, with reasoning |
| `docs/ARCHITECTURE.md` | Data flow and design notes |
| `scripts/scope_check.py` | One-off validation of the dataset offset against independent sources (needs network) |

## Running it

### Docker

> **Not verified.** The Dockerfiles and `docker-compose.yml` are provided, but the images were **not built or run** in the
> environment this project was written in (no Docker available there). Treat `docker compose up --build` as untested
> until you have run it.

```
docker compose up --build        # then open http://localhost:3000
```

### Manually (verified)

Python 3.11 or 3.12 and Node 20 or later.

```
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r backend/requirements-dev.txt

cd backend
python -m uvicorn app.main:app --port 8000          # API at http://127.0.0.1:8000/api/docs
```

```
cd frontend
npm ci
npm run dev                                          # http://localhost:5173, proxies /api to port 8000
```

Refresh the data (optional; needs network): `cd backend && python -m app.ingest --refresh`. Re-running without `--refresh`
makes no network calls but does rebuild `data/app.db`.

Deploy: `npx vercel login` then `npx vercel deploy --prod` from the repository root.

## Design decisions and assumptions

Full reasoning is in [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md). The ones to know:

- **No lookahead.** For each delivery hour the forecast is the latest WINDFOR publication with
  `publishTime + 1 minute <= cutoff` on D-1. Nothing later is ever used, and if nothing earlier exists the hour is reported
  missing rather than falling back. The 1 minute lag is deliberate conservatism: a forecast stamped 15:30:00 is not on the
  desk of someone submitting into a 15:30:00 gate.
- **Cutoffs are real gate closures**, in Europe/London time on D-1: 09:20 (EPEX 60 minute, primary), 09:50 (N2EX) and
  15:30 (EPEX 30 minute). All metrics are computed at all three and compared in the UI.
- **Native resolution.** WINDFOR is hourly and FUELHH is half-hourly, so the two half-hours inside each forecast hour are
  averaged (mean of MW, never a sum) and the forecast is never interpolated.
- **No MAPE**, because wind output approaches zero.
- **Committed snapshot** rather than live calls, as described above.

## Known limitations

- **Scope.** FUELHH is transmission-metered, BM-registered wind and excludes embedded wind, so against it the forecast
  runs high. Measured against full-fleet outturn the forecast is slightly low. The app reports FUELHH-based figures
  (evaluating the forecast as published) and states the offset on screen.
- **One month.** The correction, the band and the cutoff comparison are all estimated and scored on January 2026. They are
  in-sample, and one month cannot show they hold in other seasons.
- **Availability time.** `publishTime` is assumed to be when a forecast reaches the desk. The data cannot show real latency.
- **Daylight saving.** January has no clock change, so the scope is unaffected, but the time handling should be audited
  before extending to March or October.
- **Gate times** were supplied, not independently verified against exchange rules.
- Docker images are untested (see above). There are no front-end automated tests.

## Testing

```
cd backend
python -m pytest        # 61 tests
python -m ruff check .
```

`test_align.py` covers the no-lookahead rule (vintage selection at each gate, equality at the cutoff, no fallback to a later
vintage, a 600-case brute-force check, and the real snapshot at all three cutoffs). `test_metrics.py` checks each formula
against hand-computed values. `test_api.py` checks the endpoints, the echoed cutoff rule and clean error responses.

## AI tool disclosure

AI tools assisted in building this project.
