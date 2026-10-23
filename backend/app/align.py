"""Forecast vintage selection and resolution alignment.

The rule that must never break (CLAUDE.md 3.2, no lookahead):

    usable_forecast(t) = the row with startTime == t and the maximum publishTime
                         subject to publishTime + PUBLICATION_LAG <= decision_cutoff(D)

A forecast published after the cutoff is never used, and there is no fallback to one when
nothing earlier exists: the interval is reported as missing instead.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app import config


@dataclass(frozen=True)
class Vintage:
    publish_time: pd.Timestamp
    generation_mw: float


def decision_cutoff(delivery_date: date, cutoff: config.Cutoff) -> pd.Timestamp:
    """(D - 1 day) at the gate-closure wall-clock time in Europe/London, as a UTC timestamp."""
    local = pd.Timestamp.combine(
        pd.Timestamp(delivery_date - timedelta(days=1)).date(), cutoff.local_time
    ).tz_localize(config.LONDON)
    return local.tz_convert("UTC")


def select_vintages(
    forecasts: pd.DataFrame, targets: pd.DataFrame, lag: timedelta = config.PUBLICATION_LAG
) -> pd.DataFrame:
    """Vectorised vintage selection.

    forecasts: start_time, publish_time, generation_mw
    targets:   target_time, cutoff (one row per interval to evaluate)
    returns:   targets' rows in order, plus forecast_publish_time and forecast_mw (NaT/NaN when
               no forecast was in hand at the cutoff).
    """
    t = targets[["target_time", "cutoff"]].reset_index(drop=True).copy()
    t["_i"] = np.arange(len(t))
    m = t.merge(forecasts, left_on="target_time", right_on="start_time", how="left")
    in_hand = m["publish_time"].notna() & (m["publish_time"] + lag <= m["cutoff"])
    best = (
        m[in_hand]
        .sort_values(["_i", "publish_time"])
        .groupby("_i", sort=False)
        .tail(1)[["_i", "publish_time", "generation_mw"]]
        .rename(columns={"publish_time": "forecast_publish_time", "generation_mw": "forecast_mw"})
    )
    out = t.merge(best, on="_i", how="left").drop(columns="_i")
    return out


def select_vintage(
    forecasts: pd.DataFrame,
    target_time: pd.Timestamp,
    cutoff: pd.Timestamp,
    lag: timedelta = config.PUBLICATION_LAG,
) -> Vintage | None:
    """Scalar form of select_vintages. Returns None when no forecast was in hand."""
    row = select_vintages(
        forecasts, pd.DataFrame({"target_time": [target_time], "cutoff": [cutoff]}), lag
    ).iloc[0]
    if pd.isna(row["forecast_publish_time"]):
        return None
    return Vintage(row["forecast_publish_time"], float(row["forecast_mw"]))


def expected_index(delivery_from: date, delivery_to: date) -> pd.DataFrame:
    """Every hourly delivery interval of every delivery day (London days), as UTC."""
    parts = []
    d = delivery_from
    while d <= delivery_to:
        start = pd.Timestamp(d, tz=config.LONDON)
        end = pd.Timestamp(d + timedelta(days=1), tz=config.LONDON)
        hours = pd.date_range(start, end, freq="h", inclusive="left").tz_convert("UTC")
        parts.append(pd.DataFrame({"target_time": hours.as_unit("ns"), "delivery_date": d}))
        d += timedelta(days=1)
    return pd.concat(parts, ignore_index=True)


def hourly_actuals(actuals: pd.DataFrame) -> pd.Series:
    """Mean of the two half-hours that fall inside each hour starting at T (T and T+30min).

    The values are power in MW, so the hour is the mean, never the sum. An hour missing either
    half-hour is NaN: an incomplete pair is reported as missing, not averaged from one value.
    """
    g = (
        actuals.assign(hour=actuals["start_time"].dt.floor("h"))
        .groupby("hour")["generation_mw"]
        .agg(["mean", "count"])
    )
    return g["mean"].where(g["count"] == 2)


def build_aligned_table(
    actuals: pd.DataFrame,
    forecasts: pd.DataFrame,
    delivery_from: date,
    delivery_to: date,
    cutoff: config.Cutoff,
    lag: timedelta = config.PUBLICATION_LAG,
) -> pd.DataFrame:
    """One row per expected hourly delivery interval (outer join: nothing is silently dropped).

    Evaluation is at WINDFOR's native hourly resolution. The forecast is never interpolated.
    error = forecast - actual, so a positive error means the forecast was too high.
    """
    idx = expected_index(delivery_from, delivery_to)
    cutoffs = {d: decision_cutoff(d, cutoff) for d in idx["delivery_date"].unique()}
    idx["cutoff"] = idx["delivery_date"].map(cutoffs)
    idx["cutoff"] = pd.to_datetime(idx["cutoff"], utc=True).dt.as_unit("ns")

    t = select_vintages(forecasts, idx, lag)
    t["delivery_date"] = idx["delivery_date"].to_numpy()
    t["hour"] = t["target_time"].dt.tz_convert(config.LONDON).dt.hour
    act = hourly_actuals(actuals)
    t["actual_mw"] = t["target_time"].map(act)

    has_f, has_a = t["forecast_mw"].notna(), t["actual_mw"].notna()
    t["status"] = np.select(
        [has_f & has_a, ~has_f & has_a, has_f & ~has_a],
        ["ok", "missing_forecast", "missing_actual"],
        default="missing_both",
    )
    ok = t["status"] == "ok"
    t["error"] = np.where(ok, t["forecast_mw"] - t["actual_mw"], np.nan)
    t["abs_error"] = t["error"].abs()
    t["lead_time_h"] = (t["target_time"] - t["forecast_publish_time"]).dt.total_seconds() / 3600
    cols = [
        "target_time",
        "delivery_date",
        "hour",
        "cutoff",
        "forecast_mw",
        "forecast_publish_time",
        "lead_time_h",
        "actual_mw",
        "error",
        "abs_error",
        "status",
    ]
    return t[cols]
