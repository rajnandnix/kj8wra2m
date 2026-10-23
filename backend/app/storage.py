"""Read-only access to the committed SQLite snapshot."""
import sqlite3
from pathlib import Path

import pandas as pd


def connect_ro(path: Path) -> sqlite3.Connection:
    """Open the snapshot read-only. The deployed filesystem may not be writable."""
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def _utc(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, utc=True).dt.as_unit("ns")


def load_frames(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (actuals, forecasts) with timezone-aware UTC timestamps.

    actuals:   start_time, generation_mw           (half-hourly)
    forecasts: start_time, publish_time, generation_mw   (hourly targets, many vintages)
    """
    con = connect_ro(path)
    try:
        actuals = pd.read_sql_query(
            "SELECT start_time_utc AS start_time, generation_mw FROM actuals ORDER BY 1", con
        )
        forecasts = pd.read_sql_query(
            "SELECT start_time_utc AS start_time, publish_time_utc AS publish_time, generation_mw "
            "FROM forecasts ORDER BY 1, 2",
            con,
        )
    finally:
        con.close()
    actuals["start_time"] = _utc(actuals["start_time"])
    forecasts["start_time"] = _utc(forecasts["start_time"])
    forecasts["publish_time"] = _utc(forecasts["publish_time"])
    return actuals, forecasts


def load_meta(path: Path) -> dict[str, str]:
    con = connect_ro(path)
    try:
        return dict(con.execute("SELECT key, value FROM meta").fetchall())
    finally:
        con.close()
