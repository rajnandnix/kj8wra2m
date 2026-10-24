"""Formula tests against hand-computed values. Five rows prove the definitions.

Fixture (error = forecast - actual, MW):
    errors  = [ 100,  -50,  200,    0, -150]    sum 100, mean (bias) = 20
    |error| = [ 100,   50,  200,    0,  150]    sum 500, MAE = 100
    error^2 = [10000, 2500, 40000,  0, 22500]   sum 75000, MSE = 15000, RMSE = 122.4745
    actual  = [1000, 2000, 1500,  500, 1000]    mean 1200, nMAE = 100 / 1200 = 8.3333 %
    sorted errors [-150, -50, 0, 100, 200], linear interpolation:
        P10 = -150 + 0.4 * 100 = -110;  P50 = 0;  P90 = 100 + 0.6 * 100 = 160
    debiased: e - 20 = [80, -70, 180, -20, -170]
        MAE = 520 / 5 = 104;  RMSE = sqrt(15000 - 20^2) = sqrt(14600) = 120.8305
"""

import math

import pandas as pd
import pytest

from app import metrics

ERR = [100.0, -50.0, 200.0, 0.0, -150.0]
ACT = [1000.0, 2000.0, 1500.0, 500.0, 1000.0]


def frame(extra=()):
    base = pd.Timestamp("2026-01-15T00:00:00Z")
    rows = []
    for i, (e, a) in enumerate(zip(ERR, ACT, strict=True)):
        t = base + pd.Timedelta(hours=i * 5)  # hours 0, 5, 10, 15, 20
        rows.append(
            dict(
                target_time=t,
                delivery_date=t.date(),
                hour=t.hour,
                actual_mw=a,
                forecast_mw=a + e,
                error=e,
                abs_error=abs(e),
                status="ok",
                forecast_publish_time=t - pd.Timedelta(hours=24),
                lead_time_h=24.0,
            )
        )
    for j, status in enumerate(extra):
        t = base + pd.Timedelta(days=1, hours=j)
        rows.append(
            dict(
                target_time=t,
                delivery_date=t.date(),
                hour=t.hour,
                actual_mw=None if status != "missing_forecast" else 100.0,
                forecast_mw=None if status != "missing_actual" else 100.0,
                error=float("nan"),
                abs_error=float("nan"),
                status=status,
                forecast_publish_time=pd.NaT,
                lead_time_h=float("nan"),
            )
        )
    return pd.DataFrame(rows)


def test_headline_formulas():
    h = metrics.headline(frame())
    assert h["mae_mw"] == pytest.approx(100.0)
    assert h["rmse_mw"] == pytest.approx(math.sqrt(15000))
    assert h["bias_mw"] == pytest.approx(20.0)
    assert h["nmae_pct"] == pytest.approx(100 / 1200 * 100)
    assert h["mean_actual_mw"] == pytest.approx(1200.0)


def test_error_percentiles():
    h = metrics.headline(frame())
    assert h["p10_mw"] == pytest.approx(-110.0)
    assert h["p50_mw"] == pytest.approx(0.0)
    assert h["p90_mw"] == pytest.approx(160.0)


def test_max_abs_error_reports_its_timestamp():
    h = metrics.headline(frame())
    assert h["max_abs_error_mw"] == 200.0
    assert h["max_abs_error_time"] == pd.Timestamp("2026-01-15T10:00:00Z")


def test_debiased_metrics_remove_the_mean_error_only():
    h = metrics.headline(frame())
    assert h["debiased_mae_mw"] == pytest.approx(104.0)
    assert h["debiased_rmse_mw"] == pytest.approx(math.sqrt(14600))
    # RMSE identity: rmse^2 = bias^2 + debiased_rmse^2
    assert h["rmse_mw"] ** 2 == pytest.approx(h["bias_mw"] ** 2 + h["debiased_rmse_mw"] ** 2)


def test_coverage_counts_missing_and_excludes_incomplete_pairs():
    h = metrics.headline(frame(extra=("missing_forecast", "missing_actual", "missing_both")))
    assert h["n_expected"] == 8 and h["n_valid"] == 5
    assert h["n_missing_forecast"] == 1 and h["n_missing_actual"] == 1 and h["n_missing_both"] == 1
    assert h["coverage_pct"] == pytest.approx(5 / 8 * 100)
    assert h["mae_mw"] == pytest.approx(100.0), "incomplete pairs must not enter the metrics"


def test_full_coverage_is_100():
    assert metrics.headline(frame())["coverage_pct"] == 100.0


def test_no_valid_rows_gives_none_not_a_crash():
    h = metrics.headline(frame(extra=("missing_both",)).iloc[5:])
    assert h["n_valid"] == 0 and h["mae_mw"] is None and h["coverage_pct"] == 0.0


def test_mape_is_deliberately_absent():
    assert not any("mape" in k.lower() for k in metrics.headline(frame()))


def test_by_hour_groups_on_hour_of_day():
    g = metrics.by_hour(frame()).set_index("hour")
    assert list(g.index) == [0, 5, 10, 15, 20]
    assert g.loc[10, "mae_mw"] == 200.0 and g.loc[10, "bias_mw"] == 200.0
    assert g.loc[5, "bias_mw"] == -50.0 and g.loc[0, "n"] == 1


def test_by_level_buckets_on_actual_generation_and_reports_relative_bias():
    g = metrics.by_level(frame(), edges=(0, 1000, 1500, float("inf"))).set_index("bucket")
    # actual < 1000: only 500 (error 0). [1000,1500): 1000, 1000 (errors 100, -150).
    # >= 1500: 2000, 1500 (errors -50, 200)
    assert g.loc["< 1 GW", "n"] == 1 and g.loc["< 1 GW", "bias_mw"] == 0.0
    assert g.loc["1-1.5 GW", "n"] == 2 and g.loc["1-1.5 GW", "bias_mw"] == pytest.approx(-25.0)
    assert g.loc[">= 1.5 GW", "mae_mw"] == pytest.approx(125.0)
    assert g.loc[">= 1.5 GW", "bias_pct_of_actual"] == pytest.approx(75 / 1750 * 100)


def test_by_level_can_bucket_on_forecast_instead_of_actual():
    # forecasts = actual + error = [1100, 1950, 1700, 500, 850]
    g = metrics.by_level(frame(), edges=(0, 1000, 1500, float("inf")), basis="forecast")
    g = g.set_index("bucket")
    assert g.loc["< 1 GW", "n"] == 2  # forecasts 500 and 850: errors 0, -150
    assert g.loc["< 1 GW", "bias_mw"] == pytest.approx(-75.0)
    assert g.loc["1-1.5 GW", "n"] == 1 and g.loc["1-1.5 GW", "bias_mw"] == 100.0
    assert g.loc[">= 1.5 GW", "bias_mw"] == pytest.approx(75.0)
    with pytest.raises(ValueError):
        metrics.by_level(frame(), basis="nope")


def test_by_day_and_worst_intervals():
    d = metrics.by_day(frame(extra=("missing_forecast",)))
    assert len(d) == 2 and d.iloc[0]["n_valid"] == 5 and d.iloc[1]["n_valid"] == 0
    w = metrics.worst_intervals(frame(), n=2)
    assert list(w.abs_error) == [200.0, 150.0]


def test_histogram_counts_sum_to_valid_rows():
    h = metrics.histogram(frame(), bin_mw=100)
    assert sum(b["count"] for b in h) == 5
    assert h[0]["from_mw"] <= -150 and h[-1]["to_mw"] >= 200


def test_level_slope_of_error_on_actual():
    # perfectly proportional error: e = 0.1 * actual
    df = frame()
    df["error"] = df.actual_mw * 0.1
    df["abs_error"] = df.error.abs()
    s = metrics.level_trend(df)
    assert s["slope_mw_per_mw"] == pytest.approx(0.1)
    assert s["intercept_mw"] == pytest.approx(0.0, abs=1e-9)
    assert s["correlation"] == pytest.approx(1.0)


def test_procurement_band_from_error_quantiles():
    h = metrics.headline(frame())
    b = metrics.procurement_band(forecast_mw=1000.0, headline=h, hours=1.0)
    # realised wind = forecast - error, so it lies in [F - P90, F - P10]
    assert b["wind_low_mw"] == pytest.approx(1000 - 160)
    assert b["wind_high_mw"] == pytest.approx(1000 + 110)
    assert b["cover_p90_mw"] == pytest.approx(160.0)  # shortfall to hold thermal cover for
    assert b["cover_p90_mwh"] == pytest.approx(160.0)
    assert metrics.procurement_band(1000.0, h, hours=24.0)["cover_p90_mwh"] == pytest.approx(3840)


def test_cover_requirement_is_floored_at_zero_when_p90_error_is_negative():
    h = metrics.headline(frame())
    h = {**h, "p90_mw": -30.0}
    assert metrics.procurement_band(1000.0, h, hours=1.0)["cover_p90_mw"] == 0.0


def test_compare_cutoffs_paired_difference_and_bootstrap_is_seeded():
    a, b = frame(), frame()
    b["error"] = b.error * 0.5
    b["abs_error"] = b.error.abs()
    c1 = metrics.compare_cutoffs(a, b)
    assert c1["n_paired"] == 5
    assert c1["mae_delta_mw"] == pytest.approx(-50.0)  # b minus a: negative means b is better
    assert c1["mae_delta_pct"] == pytest.approx(-50.0)
    assert c1 == metrics.compare_cutoffs(a, b), "bootstrap must be deterministic"
    lo, hi = c1["mae_delta_ci95_mw"]
    assert lo <= -50.0 + 1e-9 and hi >= -50.0 - 1e-9


# --- conditional procurement band (quantiles per forecast-level bucket) -----------------------
#
# Two buckets on the forecast: < 1 GW and >= 1 GW. Within each, errors are chosen so the
# linear-interpolation percentiles are easy to verify by hand:
#   < 1 GW  (forecast 500):  errors [-20, -10, 0, 10, 20]   -> P10 -16, P50 0,   P90 16
#   >= 1 GW (forecast 2000): errors [100, 200, 300, 400, 500] -> P10 140, P50 300, P90 460
# A band is [forecast - P90, forecast - P10] on the realised wind, i.e. error in [P10, P90]:
#   bucket 1 holds errors -10, 0, 10 (3 of 5);  bucket 2 holds 200, 300, 400 (3 of 5).
EDGES = (0, 1000, float("inf"))


def band_frame():
    t0 = pd.Timestamp("2026-01-15T00:00:00Z")
    rows = []
    for i, (f, e) in enumerate(
        [(500, x) for x in (-20, -10, 0, 10, 20)] + [(2000, x) for x in (100, 200, 300, 400, 500)]
    ):
        t = t0 + pd.Timedelta(hours=i)
        rows.append(
            dict(target_time=t, delivery_date=t.date(), hour=t.hour, forecast_mw=float(f),
                 actual_mw=float(f - e), error=float(e), abs_error=float(abs(e)), status="ok",
                 forecast_publish_time=t - pd.Timedelta(hours=24), lead_time_h=24.0)
        )  # fmt: skip
    return pd.DataFrame(rows)


def test_conditional_quantiles_per_forecast_bucket():
    q = metrics.conditional_error_quantiles(band_frame(), edges=EDGES).set_index("bucket")
    assert list(q.index) == ["< 1 GW", ">= 1 GW"]
    assert q.loc["< 1 GW", "n"] == 5 and q.loc[">= 1 GW", "n"] == 5
    assert q.loc["< 1 GW", "p10_mw"] == pytest.approx(-16.0)
    assert q.loc["< 1 GW", "p50_mw"] == pytest.approx(0.0)
    assert q.loc["< 1 GW", "p90_mw"] == pytest.approx(16.0)
    assert q.loc[">= 1 GW", "p10_mw"] == pytest.approx(140.0)
    assert q.loc[">= 1 GW", "p50_mw"] == pytest.approx(300.0)
    assert q.loc[">= 1 GW", "p90_mw"] == pytest.approx(460.0)


def test_in_sample_coverage_is_reported_per_bucket_and_overall():
    c = metrics.conditional_band_summary(band_frame(), edges=EDGES)
    by = {b["bucket"]: b for b in c["buckets"]}
    assert by["< 1 GW"]["coverage_pct"] == pytest.approx(60.0)
    assert by[">= 1 GW"]["coverage_pct"] == pytest.approx(60.0)
    assert c["overall_coverage_pct"] == pytest.approx(60.0)
    # unconditional band over all ten errors, for comparison: P10 = -10 + ..., computed by headline
    h = metrics.headline(band_frame())
    inside = sum(
        h["p10_mw"] <= e <= h["p90_mw"] for e in [-20, -10, 0, 10, 20, 100, 200, 300, 400, 500]
    )
    assert c["unconditional_coverage_pct"] == pytest.approx(inside / 10 * 100)


def test_apply_band_uses_each_hours_own_bucket():
    q = metrics.conditional_error_quantiles(band_frame(), edges=EDGES)
    hours = pd.Series([500.0, 2000.0, 1000.0])  # 1000 sits on the left-closed edge: upper bucket
    b = metrics.apply_conditional_band(hours, q, edges=EDGES)
    assert list(b["wind_low_mw"]) == pytest.approx([500 - 16, 2000 - 460, 1000 - 460])
    assert list(b["wind_high_mw"]) == pytest.approx([500 + 16, 2000 - 140, 1000 - 140])
    assert list(b["cover_p90_mw"]) == pytest.approx([16.0, 460.0, 460.0])
    assert list(b["bucket"]) == ["< 1 GW", ">= 1 GW", ">= 1 GW"]


def test_day_band_summary_energy_is_sum_over_hours_of_p90_cover():
    q = metrics.conditional_error_quantiles(band_frame(), edges=EDGES)
    day = metrics.day_band(pd.Series([500.0, 2000.0]), q, edges=EDGES, hours_each=1.0)
    assert day["cover_p90_mw"] == pytest.approx((16 + 460) / 2)  # mean MW across the hours
    assert day["cover_p90_mwh"] == pytest.approx(16 + 460)  # MW x 1 h, summed
    assert day["forecast_mw"] == pytest.approx(1250.0)


def test_p90_cover_is_floored_at_zero_per_hour():
    q = metrics.conditional_error_quantiles(band_frame(), edges=EDGES).copy()
    q.loc[q.bucket == "< 1 GW", "p90_mw"] = -30.0
    b = metrics.apply_conditional_band(pd.Series([500.0]), q, edges=EDGES)
    assert b["cover_p90_mw"].iloc[0] == 0.0


# --- per-day comparison of two cutoffs, and large-miss counts --------------------------------


def two_day(a_scale: float, b_scale: float, day2_b_scale: float):
    """Same hand fixture on two delivery days. Cutoff B halves day 1 errors and scales day 2."""
    d1, d2 = frame(), frame()
    shift = pd.Timedelta(days=1)
    d2["target_time"] = d2["target_time"] + shift
    d2["delivery_date"] = d2["target_time"].dt.date
    a = pd.concat([d1, d2], ignore_index=True)
    b = a.copy()
    day1 = b["delivery_date"] == d1["delivery_date"].iloc[0]
    b.loc[day1, "error"] = b.loc[day1, "error"] * b_scale
    b.loc[~day1, "error"] = b.loc[~day1, "error"] * day2_b_scale
    b["abs_error"] = b["error"].abs()
    a["error"] = a["error"] * a_scale
    a["abs_error"] = a["error"].abs()
    return a, b


def test_day_comparison_reports_days_that_get_worse_not_just_the_average():
    a, b = two_day(1.0, 0.5, 1.5)  # day 1 halves (better), day 2 grows 50% (worse)
    c = metrics.day_comparison(a, b)
    days = {r["delivery_date"]: r for r in c["by_day"]}
    d1, d2 = sorted(days)
    assert days[d1]["delta_mw"] == pytest.approx(-50.0) and days[d2]["delta_mw"] == pytest.approx(
        50.0
    )
    assert days[d1]["mae_baseline_mw"] == pytest.approx(100.0)
    assert days[d2]["mae_alternative_mw"] == pytest.approx(150.0)
    assert (c["days_improved"], c["days_worse"], c["days_unchanged"]) == (1, 1, 0)
    # the pooled average hides it: (-50 + 50) / 2 = 0
    assert metrics.compare_cutoffs(a, b)["mae_delta_mw"] == pytest.approx(0.0)


def test_gain_without_the_single_best_day():
    a, b = two_day(1.0, 0.5, 0.9)  # day 1: 100 -> 50 (-50), day 2: 100 -> 90 (-10)
    c = metrics.day_comparison(a, b)
    # pooled: (-50 - 10) / 2 = -30 MW on a baseline MAE of 100 (-30%)
    assert metrics.compare_cutoffs(a, b)["mae_delta_pct"] == pytest.approx(-30.0)
    # drop the best day (day 1): only day 2 remains, -10 on 100 = -10%
    assert c["mae_delta_pct_without_best_day"] == pytest.approx(-10.0)
    assert c["best_day"] == sorted(r["delivery_date"] for r in c["by_day"])[0]


def test_by_day_counts_large_misses():
    d = metrics.by_day(frame(), large_mw=150.0)
    assert d.iloc[0]["n_large_misses"] == 2  # |error| 200 and 150
    assert metrics.by_day(frame()).iloc[0]["n_large_misses"] == 0  # default threshold is 4,000 MW
