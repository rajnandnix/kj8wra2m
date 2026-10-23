"""Fetch Elexon BMRS data, cache raw responses, build the SQLite snapshot.

    python -m app.ingest             # uses data/raw/ cache, zero network calls when complete
    python -m app.ingest --refresh   # re-fetch everything and rebuild

Verified API behaviour this module relies on (docs/ASSUMPTIONS.md section 2):
  * both datasets return a bare JSON array;
  * `publishDateTimeFrom/To` (WINDFOR) and `settlementDateFrom/To` (FUELHH) filter, both ends
    inclusive;
  * unknown parameters such as `from`/`to` are silently ignored, so every response is
    validated against the window that was asked for.
"""
import argparse
import json
import sqlite3
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd

from app import config

MAX_ATTEMPTS = 5
PAUSE_S = 0.5
_network_calls = 0


class IngestError(RuntimeError):
    pass


def _iso(d: datetime) -> str:
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _chunks(first: date, last: date, days: int) -> list[tuple[date, date]]:
    """Split [first, last] (inclusive) into consecutive inclusive date ranges."""
    out, s = [], first
    while s <= last:
        e = min(s + timedelta(days=days - 1), last)
        out.append((s, e))
        s = e + timedelta(days=1)
    return out


def _get(client: httpx.Client, url: str, params: dict) -> bytes:
    """GET with retry and exponential backoff on 429 and 5xx. Other 4xx fail loudly."""
    global _network_calls
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            _network_calls += 1
            r = client.get(url, params=params)
        except httpx.TransportError as exc:
            if attempt == MAX_ATTEMPTS:
                raise IngestError(f"network error after {attempt} attempts: {exc}") from exc
        else:
            if r.status_code == 200:
                return r.content
            retryable = r.status_code == 429 or r.status_code >= 500
            if not retryable or attempt == MAX_ATTEMPTS:
                raise IngestError(f"{r.request.url} -> HTTP {r.status_code}: {r.text[:200]}")
        time.sleep(2**attempt)
    raise AssertionError("unreachable")


def _cached(client: httpx.Client, url: str, params: dict, path: Path, refresh: bool) -> list[dict]:
    """Return parsed rows, writing the raw response to `path` before parsing."""
    if path.exists() and not refresh:
        raw = path.read_bytes()
    else:
        raw = _get(client, url, params)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        time.sleep(PAUSE_S)
    body = json.loads(raw)
    if not isinstance(body, list):
        raise IngestError(f"{path.name}: expected a JSON array, got {type(body).__name__}")
    return body


def fetch_windfor(client: httpx.Client, refresh: bool) -> pd.DataFrame:
    """All WINDFOR publications from the fetch start to the end of the last decision day."""
    rows: list[dict] = []
    for s, e in _chunks(config.FETCH_FORECAST_FROM, config.DECISION_TO, config.FETCH_CHUNK_DAYS):
        lo = datetime(s.year, s.month, s.day, tzinfo=UTC)
        hi = datetime(e.year, e.month, e.day, tzinfo=UTC) + timedelta(days=1) - timedelta(seconds=1)
        params = {"publishDateTimeFrom": _iso(lo), "publishDateTimeTo": _iso(hi)}
        path = config.RAW_DIR / f"WINDFOR_{s:%Y%m%d}_{e:%Y%m%d}.json"
        chunk = _cached(client, config.WINDFOR_URL, params, path, refresh)
        for r in chunk:
            pub = pd.Timestamp(r["publishTime"])
            if not (pd.Timestamp(lo) <= pub <= pd.Timestamp(hi)):
                raise IngestError(f"{path.name}: publishTime {pub} outside requested window")
        rows += chunk
    return _frame(rows, ["startTime", "publishTime", "generation"], "WINDFOR")


def fetch_fuelhh(client: httpx.Client, refresh: bool) -> pd.DataFrame:
    """FUELHH WIND rows for every delivery day, selected by settlement date."""
    rows: list[dict] = []
    for s, e in _chunks(config.DELIVERY_FROM, config.DELIVERY_TO, config.FETCH_CHUNK_DAYS):
        params = {
            "settlementDateFrom": s.isoformat(),
            "settlementDateTo": e.isoformat(),
            "fuelType": config.FUEL_TYPE,
        }
        path = config.RAW_DIR / f"FUELHH_{config.FUEL_TYPE}_{s:%Y%m%d}_{e:%Y%m%d}.json"
        chunk = _cached(client, config.FUELHH_URL, params, path, refresh)
        for r in chunk:
            if r["fuelType"] != config.FUEL_TYPE:
                raise IngestError(f"{path.name}: unexpected fuelType {r['fuelType']}")
            if not (s.isoformat() <= r["settlementDate"] <= e.isoformat()):
                raise IngestError(f"{path.name}: settlementDate {r['settlementDate']} out of range")
        rows += chunk
    return _frame(rows, ["startTime", "generation"], "FUELHH")


def _frame(rows: list[dict], cols: list[str], name: str) -> pd.DataFrame:
    if not rows:
        raise IngestError(f"{name}: no rows returned")
    df = pd.DataFrame(rows)[cols]
    for c in ("startTime", "publishTime"):
        if c in df:
            df[c] = pd.to_datetime(df[c], utc=True)
    if df.generation.isna().any():
        raise IngestError(f"{name}: null generation values")
    return df


def dedupe(df: pd.DataFrame, key: list[str], name: str) -> tuple[pd.DataFrame, int]:
    """Drop exact duplicate rows, then require `key` to be unique. Fail loudly otherwise."""
    before = len(df)
    df = df.drop_duplicates().reset_index(drop=True)
    if df.duplicated(key).any():
        raise IngestError(f"{name}: rows share {key} but differ in other columns")
    return df, before - len(df)


def _ts(s: pd.Series) -> pd.Series:
    return s.dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_db(actuals: pd.DataFrame, forecasts: pd.DataFrame, dups: dict[str, int]) -> None:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = config.DB_PATH.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript(
        """
        CREATE TABLE actuals (start_time_utc TEXT PRIMARY KEY, generation_mw REAL NOT NULL);
        CREATE TABLE forecasts (
            start_time_utc TEXT NOT NULL, publish_time_utc TEXT NOT NULL,
            generation_mw REAL NOT NULL, PRIMARY KEY (start_time_utc, publish_time_utc));
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """
    )
    a = pd.DataFrame({"s": _ts(actuals.startTime), "g": actuals.generation.astype(float)})
    f = pd.DataFrame(
        {
            "s": _ts(forecasts.startTime),
            "p": _ts(forecasts.publishTime),
            "g": forecasts.generation.astype(float),
        }
    )
    con.executemany("INSERT INTO actuals VALUES (?, ?)", a.itertuples(index=False))
    con.executemany("INSERT INTO forecasts VALUES (?, ?, ?)", f.itertuples(index=False))
    con.execute("CREATE INDEX idx_actuals_start ON actuals (start_time_utc)")
    con.execute("CREATE INDEX idx_forecasts_start_pub ON forecasts (start_time_utc, publish_time_utc)")
    meta = {
        "build_timestamp_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_windfor": config.WINDFOR_URL,
        "source_fuelhh": f"{config.FUELHH_URL}?fuelType={config.FUEL_TYPE}",
        "decision_from": config.DECISION_FROM.isoformat(),
        "decision_to": config.DECISION_TO.isoformat(),
        "delivery_from": config.DELIVERY_FROM.isoformat(),
        "delivery_to": config.DELIVERY_TO.isoformat(),
        "forecast_fetch_from": config.FETCH_FORECAST_FROM.isoformat(),
        "actuals_rows": str(len(a)),
        "forecast_rows": str(len(f)),
        "forecast_publications": str(forecasts.publishTime.nunique()),
        "boundary_duplicates_dropped": json.dumps(dups),
    }
    con.executemany("INSERT INTO meta VALUES (?, ?)", meta.items())
    con.commit()
    con.close()
    tmp.replace(config.DB_PATH)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="ignore data/raw cache and re-fetch")
    args = ap.parse_args(argv)

    with httpx.Client(timeout=120, headers={"Accept": "application/json"}) as client:
        windfor = fetch_windfor(client, args.refresh)
        fuelhh = fetch_fuelhh(client, args.refresh)
    windfor, d1 = dedupe(windfor, ["startTime", "publishTime"], "WINDFOR")
    fuelhh, d2 = dedupe(fuelhh, ["startTime"], "FUELHH")
    build_db(fuelhh, windfor, {"WINDFOR": d1, "FUELHH": d2})

    expected = ((config.DELIVERY_TO - config.DELIVERY_FROM).days + 1) * 48
    print(f"network calls: {_network_calls}")
    print(f"actuals: {len(fuelhh)} rows (expected {expected} half-hours, {len(fuelhh) / expected:.1%})")
    print(
        f"forecasts: {len(windfor)} rows, {windfor.publishTime.nunique()} publications, "
        f"{windfor.startTime.min()} -> {windfor.startTime.max()}"
    )
    print(f"boundary duplicates dropped: WINDFOR={d1} FUELHH={d2}")
    print(f"wrote {config.DB_PATH}")


if __name__ == "__main__":
    main()
