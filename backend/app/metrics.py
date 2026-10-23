"""Accuracy metrics and breakdowns. Pure functions over the aligned table: no I/O.

Sign convention everywhere: error = forecast - actual. Positive error means the forecast was
too high, so the team under-procured from the day-ahead market.

MAPE is deliberately not provided: wind output approaches zero, which makes it explode.
"""

import numpy as np
import pandas as pd

from app import config

_Q = config.PERCENTILES


def _f(x) -> float | None:
    """numpy scalar to plain float, NaN to None."""
    return None if x is None or pd.isna(x) else float(x)


def _valid(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["status"] == "ok"]


def _empty_headline(df: pd.DataFrame) -> dict:
    return {
        "mae_mw": None,
        "rmse_mw": None,
        "bias_mw": None,
        "nmae_pct": None,
        "mean_actual_mw": None,
        "mean_forecast_mw": None,
        "p10_mw": None,
        "p50_mw": None,
        "p90_mw": None,
        "max_abs_error_mw": None,
        "max_abs_error_time": None,
        "debiased_mae_mw": None,
        "debiased_rmse_mw": None,
        "mean_lead_time_h": None,
    }


def headline(df: pd.DataFrame) -> dict:
    """Headline metrics over the valid (complete-pair) rows, plus coverage accounting."""
    n_expected = len(df)
    status = df["status"].value_counts()
    v = _valid(df)
    out = {
        "n_expected": n_expected,
        "n_valid": len(v),
        "n_missing_forecast": int(status.get("missing_forecast", 0)),
        "n_missing_actual": int(status.get("missing_actual", 0)),
        "n_missing_both": int(status.get("missing_both", 0)),
        "coverage_pct": (len(v) / n_expected * 100.0) if n_expected else 0.0,
    }
    if v.empty:
        return {**out, **_empty_headline(df)}

    e = v["error"].to_numpy(dtype=float)
    a = v["actual_mw"].to_numpy(dtype=float)
    bias = e.mean()
    mae = np.abs(e).mean()
    p10, p50, p90 = np.percentile(e, _Q)  # linear interpolation between order statistics
    worst = v.loc[v["abs_error"].idxmax()]
    return {
        **out,
        "mae_mw": _f(mae),
        "rmse_mw": _f(np.sqrt((e**2).mean())),
        "bias_mw": _f(bias),
        "nmae_pct": _f(mae / a.mean() * 100.0),
        "mean_actual_mw": _f(a.mean()),
        "mean_forecast_mw": _f(v["forecast_mw"].mean()),
        "p10_mw": _f(p10),
        "p50_mw": _f(p50),
        "p90_mw": _f(p90),
        "max_abs_error_mw": _f(worst["abs_error"]),
        "max_abs_error_time": worst["target_time"],
        # Separates a standing offset from forecast skill: what is left after subtracting the
        # mean error. This is a correction the client can apply, not a model of our own.
        "debiased_mae_mw": _f(np.abs(e - bias).mean()),
        "debiased_rmse_mw": _f(np.sqrt(((e - bias) ** 2).mean())),
        "mean_lead_time_h": _f(v["lead_time_h"].mean()),
    }


def _group_stats(g: pd.core.groupby.DataFrameGroupBy) -> pd.DataFrame:
    return g.agg(
        n=("error", "size"),
        mae_mw=("abs_error", "mean"),
        rmse_mw=("error", lambda s: float(np.sqrt((s**2).mean()))),
        bias_mw=("error", "mean"),
        mean_actual_mw=("actual_mw", "mean"),
        mean_forecast_mw=("forecast_mw", "mean"),
    )


def by_hour(df: pd.DataFrame) -> pd.DataFrame:
    """Error by local hour of the delivery day."""
    return _group_stats(_valid(df).groupby("hour")).reset_index()


def _bucket_label(lo: float, hi: float) -> str:
    g = lambda x: f"{x / 1000:g}"  # noqa: E731
    if lo <= 0:
        return f"< {g(hi)} GW"
    if np.isinf(hi):
        return f">= {g(lo)} GW"
    return f"{g(lo)}-{g(hi)} GW"


def by_level(
    df: pd.DataFrame, edges=config.LEVEL_BUCKET_EDGES_MW, basis: str = "actual"
) -> pd.DataFrame:
    """Error by generation level, buckets left-closed.

    basis="actual" buckets on realised MW (the brief). Conditioning on the outcome makes low
    buckets look biased high even for an unbiased noisy forecast, so basis="forecast" buckets
    on the forecast, which is what a trader knows at decision time.
    """
    if basis not in ("actual", "forecast"):
        raise ValueError("basis must be 'actual' or 'forecast'")
    col = "actual_mw" if basis == "actual" else "forecast_mw"
    v = _valid(df).copy()
    labels = [_bucket_label(lo, hi) for lo, hi in zip(edges[:-1], edges[1:], strict=True)]
    v["bucket"] = pd.cut(v[col], bins=list(edges), labels=labels, right=False)
    g = _group_stats(v.groupby("bucket", observed=False)).reset_index()
    g["bucket"] = g["bucket"].astype(str)
    g["from_mw"] = list(edges[:-1])
    g["to_mw"] = [None if np.isinf(x) else x for x in edges[1:]]
    g["bias_pct_of_actual"] = g["bias_mw"] / g["mean_actual_mw"] * 100.0
    g["bias_pct_of_forecast"] = g["bias_mw"] / g["mean_forecast_mw"] * 100.0
    g["n"] = g["n"].fillna(0).astype(int)
    return g


def by_day(df: pd.DataFrame) -> pd.DataFrame:
    """Error per delivery day. Days with no valid pair are kept (n_valid 0)."""
    rows = []
    for day, g in df.groupby("delivery_date", sort=True):
        v = _valid(g)
        e = v["error"].to_numpy(dtype=float)
        rows.append(
            {
                "delivery_date": day,
                "n_expected": len(g),
                "n_valid": len(v),
                "mae_mw": _f(np.abs(e).mean()) if len(v) else None,
                "rmse_mw": _f(np.sqrt((e**2).mean())) if len(v) else None,
                "bias_mw": _f(e.mean()) if len(v) else None,
                "mean_actual_mw": _f(v["actual_mw"].mean()) if len(v) else None,
                "max_abs_error_mw": _f(np.abs(e).max()) if len(v) else None,
            }
        )
    return pd.DataFrame(rows)


def histogram(df: pd.DataFrame, bin_mw: float = config.HISTOGRAM_BIN_MW) -> list[dict]:
    e = _valid(df)["error"].to_numpy(dtype=float)
    if e.size == 0:
        return []
    lo = np.floor(e.min() / bin_mw) * bin_mw
    hi = max(np.ceil(e.max() / bin_mw) * bin_mw, lo + bin_mw)
    edges = np.arange(lo, hi + bin_mw / 2, bin_mw)
    counts, edges = np.histogram(e, bins=edges)
    return [
        {"from_mw": float(a), "to_mw": float(b), "count": int(c)}
        for a, b, c in zip(edges[:-1], edges[1:], counts, strict=True)
    ]


def worst_intervals(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    cols = [
        "target_time",
        "forecast_mw",
        "actual_mw",
        "error",
        "abs_error",
        "forecast_publish_time",
    ]
    return _valid(df).sort_values("abs_error", ascending=False).head(n)[cols].reset_index(drop=True)


def level_trend(df: pd.DataFrame, basis: str = "actual") -> dict:
    """Least-squares line error = intercept + slope * level (actual or forecast, per `basis`).

    Distinguishes explanations for a systematic offset: a constant MW offset has slope ~0, a
    proportional (scale/scope) offset has intercept ~0 and constant relative bias, and a
    curtailment-like offset grows faster than proportionally at high output.
    """
    v = _valid(df)
    if len(v) < 3:
        return {
            "slope_mw_per_mw": None,
            "intercept_mw": None,
            "correlation": None,
            "r_squared": None,
        }
    col = "actual_mw" if basis == "actual" else "forecast_mw"
    x, e = v[col].to_numpy(dtype=float), v["error"].to_numpy(dtype=float)
    slope, intercept = np.polyfit(x, e, 1)
    corr = np.corrcoef(x, e)[0, 1]
    return {
        "slope_mw_per_mw": _f(slope),
        "intercept_mw": _f(intercept),
        "correlation": _f(corr),
        "r_squared": _f(corr**2),
    }


def procurement_band(
    forecast_mw: float, headline: dict, hours: float = config.INTERVAL_HOURS
) -> dict:
    """Turn the empirical error distribution into a band around a forecast (brief section 3.5).

    realised = forecast - error, so the realised wind lies between forecast - P90(error) and
    forecast - P10(error) for 80% of historical intervals. The thermal cover to hold at P90 is
    the P90 shortfall (forecast minus realised), floored at zero. This is an empirical band from
    the January 2026 error quantiles, not a probabilistic forecast.
    """
    p10, p90 = headline["p10_mw"], headline["p90_mw"]
    cover = max(p90, 0.0)
    return {
        "forecast_mw": forecast_mw,
        "wind_low_mw": forecast_mw - p90,
        "wind_high_mw": forecast_mw - p10,
        "cover_low_mw": p10,
        "cover_high_mw": p90,
        "cover_p90_mw": cover,
        "cover_p90_mwh": cover * hours,
        "hours": hours,
    }


def compare_cutoffs(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    """Paired comparison of two cutoffs on the intervals valid under both. Deltas are b minus a,
    so a negative delta means b is better. The CI is a day-block bootstrap (resampling whole
    delivery days, since errors within a day are correlated), seeded for reproducibility."""
    m = _valid(a)[["target_time", "delivery_date", "error"]].merge(
        _valid(b)[["target_time", "error"]], on="target_time", suffixes=("_a", "_b")
    )
    n = len(m)
    if n == 0:
        return {"n_paired": 0}
    ea, eb = m["error_a"].to_numpy(float), m["error_b"].to_numpy(float)
    mae_a, mae_b = np.abs(ea).mean(), np.abs(eb).mean()
    rmse_a, rmse_b = np.sqrt((ea**2).mean()), np.sqrt((eb**2).mean())
    dmae_a, dmae_b = np.abs(ea - ea.mean()).mean(), np.abs(eb - eb.mean()).mean()

    days = m.groupby("delivery_date")
    sa = days["error_a"].apply(lambda s: np.abs(s).sum()).to_numpy(float)
    sb = days["error_b"].apply(lambda s: np.abs(s).sum()).to_numpy(float)
    cnt = days.size().to_numpy(float)
    rng = np.random.default_rng(config.BOOTSTRAP_SEED)
    idx = rng.integers(0, len(cnt), size=(config.BOOTSTRAP_RESAMPLES, len(cnt)))
    tot = cnt[idx].sum(axis=1)
    ra, rb = sa[idx].sum(axis=1) / tot, sb[idx].sum(axis=1) / tot
    delta = rb - ra
    pct = delta / ra * 100.0
    return {
        "n_paired": n,
        "mae_a_mw": float(mae_a),
        "mae_b_mw": float(mae_b),
        "mae_delta_mw": float(mae_b - mae_a),
        "mae_delta_pct": float((mae_b - mae_a) / mae_a * 100.0),
        "mae_delta_ci95_mw": (float(np.percentile(delta, 2.5)), float(np.percentile(delta, 97.5))),
        "mae_delta_ci95_pct": (float(np.percentile(pct, 2.5)), float(np.percentile(pct, 97.5))),
        "rmse_delta_mw": float(rmse_b - rmse_a),
        "rmse_delta_pct": float((rmse_b - rmse_a) / rmse_a * 100.0),
        "debiased_mae_delta_mw": float(dmae_b - dmae_a),
        "bias_delta_mw": float(eb.mean() - ea.mean()),
        "share_intervals_improved_pct": float((np.abs(eb) < np.abs(ea)).mean() * 100.0),
        "share_days_improved_pct": float((sb < sa).mean() * 100.0),
    }
