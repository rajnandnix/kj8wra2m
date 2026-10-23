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
