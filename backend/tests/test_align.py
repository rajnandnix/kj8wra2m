"""No-lookahead tests. Highest priority in the project.

Rule under test: for target time t and decision cutoff c, the usable forecast is the row with
startTime == t and the maximum publishTime subject to publishTime + lag <= c. Nothing published
later is ever used, and there is no fallback to a later vintage.
"""

import random
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app import config
from app.align import (
    build_aligned_table,
    decision_cutoff,
    hourly_actuals,
    select_vintage,
    select_vintages,
)

UTC = "UTC"
NO_LAG = timedelta(0)
LAG = config.PUBLICATION_LAG


def ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz=UTC)


TARGET = ts("2026-01-15T12:00:00Z")  # delivery day 15 Jan, so decisions are on 14 Jan

# Vintages straddling every GB day-ahead gate on 14 Jan, plus one from before and one from
# after the decision day. The MW value encodes the vintage so a wrong pick is obvious.
VINTAGES = {
    "2026-01-13T22:30:00Z": 90.0,
    "2026-01-14T04:30:00Z": 100.0,
    "2026-01-14T07:30:00Z": 110.0,
    "2026-01-14T09:30:00Z": 120.0,
    "2026-01-14T11:30:00Z": 130.0,
    "2026-01-14T15:30:00Z": 140.0,
    "2026-01-14T18:30:00Z": 150.0,
    "2026-01-15T02:30:00Z": 160.0,  # after every cutoff: must never be used
}


@pytest.fixture
def forecasts() -> pd.DataFrame:
    rows = [(TARGET, ts(p), mw) for p, mw in VINTAGES.items()]
    # noise: other target hours and a past-dated row must not leak into TARGET
    rows += [(TARGET + pd.Timedelta(hours=1), ts("2026-01-14T09:30:00Z"), 999.0)]
    return pd.DataFrame(rows, columns=["start_time", "publish_time", "generation_mw"])


def pick(forecasts, cutoff: str, lag=LAG):
    v = select_vintage(forecasts, TARGET, ts(cutoff), lag)
    return None if v is None else (v.publish_time, v.generation_mw)


# --- core cases from brief section 3.2 ------------------------------------------------------------


def test_picks_latest_vintage_before_cutoff_not_the_latest_overall(forecasts):
    # 09:20 gate: 09:30 and everything after is the future, 07:30 is the latest in hand.
    assert pick(forecasts, "2026-01-14T09:20:00Z") == (ts("2026-01-14T07:30:00Z"), 110.0)


def test_later_cutoffs_admit_later_vintages(forecasts):
    assert pick(forecasts, "2026-01-14T09:50:00Z") == (ts("2026-01-14T09:30:00Z"), 120.0)
    assert pick(forecasts, "2026-01-14T15:40:00Z") == (ts("2026-01-14T15:30:00Z"), 140.0)


def test_publish_exactly_at_cutoff_is_inclusive_when_lag_is_zero(forecasts):
    assert pick(forecasts, "2026-01-14T09:30:00Z", NO_LAG) == (ts("2026-01-14T09:30:00Z"), 120.0)


def test_publish_exactly_at_cutoff_is_not_in_hand_with_default_lag(forecasts):
    # the 15:30 gate coincides with the 15:30 publication: the 11:30 vintage must be used
    assert pick(forecasts, "2026-01-14T15:30:00Z") == (ts("2026-01-14T11:30:00Z"), 130.0)
    assert pick(forecasts, "2026-01-14T09:30:00Z") == (ts("2026-01-14T07:30:00Z"), 110.0)


def test_publish_plus_lag_exactly_equal_cutoff_is_usable(forecasts):
    # comparison operator is <=: publish 09:30 + 1 min == cutoff 09:31
    assert pick(forecasts, "2026-01-14T09:31:00Z") == (ts("2026-01-14T09:30:00Z"), 120.0)
    assert pick(forecasts, "2026-01-14T09:30:59Z") == (ts("2026-01-14T07:30:00Z"), 110.0)


def test_no_forecast_before_cutoff_returns_none_and_never_falls_back_to_later(forecasts):
    # earliest vintage is 13 Jan 22:30. A cutoff before it must NOT return the next one.
    assert pick(forecasts, "2026-01-13T22:29:00Z") is None
    assert pick(forecasts, "2025-12-01T00:00:00Z") is None


def test_target_with_no_forecast_at_all_returns_none(forecasts):
    other = TARGET + pd.Timedelta(hours=5)
    assert select_vintage(forecasts, other, ts("2026-01-14T09:20:00Z")) is None


def test_empty_forecast_table_returns_none():
    empty = pd.DataFrame(
        {
            "start_time": pd.to_datetime([], utc=True),
            "publish_time": pd.to_datetime([], utc=True),
            "generation_mw": [],
        }
    )
    assert select_vintage(empty, TARGET, ts("2026-01-14T09:20:00Z")) is None


def test_exhaustive_never_uses_a_vintage_published_after_the_cutoff(forecasts):
    """Brute-force oracle across 600 random cutoffs and both lag settings."""
    rng = random.Random(7)
    base = ts("2026-01-13T12:00:00Z")
    for _ in range(600):
        cutoff = base + pd.Timedelta(minutes=rng.randrange(0, 60 * 48))
        for lag in (NO_LAG, LAG):
            got = select_vintage(forecasts, TARGET, cutoff, lag)
            eligible = [(ts(p), mw) for p, mw in VINTAGES.items() if ts(p) + lag <= cutoff]
            if not eligible:
                assert got is None
            else:
                want = max(eligible)
                assert got is not None
                assert got.publish_time + lag <= cutoff, "LOOKAHEAD LEAK"
                assert (got.publish_time, got.generation_mw) == want


def test_vectorised_selection_matches_scalar(forecasts):
    cutoffs = [
        "2026-01-13T10:00:00Z",
        "2026-01-14T09:20:00Z",
        "2026-01-14T09:50:00Z",
        "2026-01-14T15:30:00Z",
        "2026-01-16T00:00:00Z",
    ]
    targets = pd.DataFrame(
        {"target_time": [TARGET] * len(cutoffs), "cutoff": [ts(c) for c in cutoffs]}
    )
    out = select_vintages(forecasts, targets, LAG)
    for i, c in enumerate(cutoffs):
        want = pick(forecasts, c)
        got = out.iloc[i]
        if want is None:
            assert pd.isna(got.forecast_publish_time) and pd.isna(got.forecast_mw)
        else:
            assert (got.forecast_publish_time, got.forecast_mw) == want


# --- cutoff construction -------------------------------------------------------------------------


def test_decision_cutoff_is_d_minus_one_london_time_in_utc():
    c = decision_cutoff(date(2026, 1, 15), config.CUTOFFS["epex60"])
    assert c == ts("2026-01-14T09:20:00Z")  # GMT: London == UTC in January
    assert decision_cutoff(date(2026, 1, 15), config.CUTOFFS["n2ex"]) == ts("2026-01-14T09:50:00Z")
    assert decision_cutoff(date(2026, 1, 15), config.CUTOFFS["epex30"]) == ts(
        "2026-01-14T15:30:00Z"
    )


def test_decision_cutoff_converts_london_summer_time():
    # not used by the January scope, but the conversion must be right if the window moves
    c = decision_cutoff(date(2026, 7, 15), config.CUTOFFS["epex60"])
    assert c == ts("2026-07-14T08:20:00Z")


def test_cutoffs_are_configured_in_one_place():
    assert config.PRIMARY_CUTOFF == "epex60"
    assert [(k, f"{c.local_time:%H:%M}") for k, c in config.CUTOFFS.items()] == [
        ("epex60", "09:20"),
        ("n2ex", "09:50"),
        ("epex30", "15:30"),
    ]


# --- resolution alignment (brief section 3.3) -----------------------------------------------------


def test_hourly_actual_is_mean_of_two_half_hours_not_sum():
    a = pd.DataFrame(
        {
            "start_time": [ts("2026-01-15T12:00:00Z"), ts("2026-01-15T12:30:00Z")],
            "generation_mw": [1000.0, 2000.0],
        }
    )
    h = hourly_actuals(a)
    assert h[ts("2026-01-15T12:00:00Z")] == 1500.0


def test_hourly_actual_is_missing_if_either_half_hour_is_missing():
    a = pd.DataFrame({"start_time": [ts("2026-01-15T12:00:00Z")], "generation_mw": [1000.0]})
    h = hourly_actuals(a)
    assert pd.isna(h.get(ts("2026-01-15T12:00:00Z"), np.nan))


# --- aligned table: outer join, statuses, signs, lead time ---


def mini_inputs():
    day = ts("2026-01-15T00:00:00Z")
    hours = [day + pd.Timedelta(hours=h) for h in range(24)]
    pub = ts("2026-01-14T07:30:00Z")
    late = ts("2026-01-14T09:30:00Z")  # after the 09:20 cutoff
    f = [(h, pub, 1000.0 + h.hour) for h in hours if h.hour != 3]  # hour 03 has no forecast
    f += [(h, late, 5000.0) for h in hours]  # decoy vintage: must never be chosen at 09:20
    forecasts = pd.DataFrame(f, columns=["start_time", "publish_time", "generation_mw"])
    a = []
    for h in hours:
        if h.hour == 5:
            continue  # hour 05 has no actuals at all
        a.append((h, 900.0))
        if h.hour != 7:  # hour 07 has only one half-hour: incomplete pair
            a.append((h + pd.Timedelta(minutes=30), 900.0))
    actuals = pd.DataFrame(a, columns=["start_time", "generation_mw"])
    return actuals, forecasts


def test_aligned_table_is_outer_join_with_every_expected_hour_and_explicit_status():
    actuals, forecasts = mini_inputs()
    cutoff = config.CUTOFFS["epex60"]
    t = build_aligned_table(actuals, forecasts, date(2026, 1, 15), date(2026, 1, 15), cutoff)
    assert len(t) == 24  # nothing silently dropped
    s = t.set_index(t.target_time.dt.hour).status
    assert s[3] == "missing_forecast"
    assert s[5] == "missing_actual" and s[7] == "missing_actual"
    assert (s.drop([3, 5, 7]) == "ok").all()
    assert t.status.value_counts().to_dict() == {
        "ok": 21,
        "missing_forecast": 1,
        "missing_actual": 2,
    }


def test_aligned_table_never_uses_the_decoy_late_vintage():
    actuals, forecasts = mini_inputs()
    t = build_aligned_table(
        actuals, forecasts, date(2026, 1, 15), date(2026, 1, 15), config.CUTOFFS["epex60"]
    )
    assert (t.forecast_publish_time.dropna() == ts("2026-01-14T07:30:00Z")).all()
    assert (
        t.forecast_publish_time.dropna() + LAG <= t.cutoff[t.forecast_publish_time.notna()]
    ).all()
    # with the 09:50 gate the decoy IS in hand, proving the cutoff alone made the difference
    t2 = build_aligned_table(
        actuals, forecasts, date(2026, 1, 15), date(2026, 1, 15), config.CUTOFFS["n2ex"]
    )
    assert (t2.forecast_mw == 5000.0).all()


def test_error_sign_and_lead_time():
    actuals, forecasts = mini_inputs()
    t = build_aligned_table(
        actuals, forecasts, date(2026, 1, 15), date(2026, 1, 15), config.CUTOFFS["epex60"]
    )
    r = t[t.target_time == ts("2026-01-15T12:00:00Z")].iloc[0]
    assert r.forecast_mw == 1012.0 and r.actual_mw == 900.0
    assert r.error == 112.0, "error = forecast - actual; positive means forecast too high"
    assert r.abs_error == 112.0
    assert r.lead_time_h == 28.5  # 07:30 on 14 Jan to 12:00 on 15 Jan


def test_aligned_table_has_one_row_per_day_per_hour_over_several_days():
    actuals, forecasts = mini_inputs()
    t = build_aligned_table(
        actuals, forecasts, date(2026, 1, 14), date(2026, 1, 16), config.CUTOFFS["epex60"]
    )
    assert len(t) == 72
    assert t.delivery_date.nunique() == 3


# --- the real snapshot: no leakage anywhere, at every configured cutoff --------------------------


@pytest.mark.skipif(not config.DB_PATH.exists(), reason="snapshot not built")
@pytest.mark.parametrize("key", list(config.CUTOFFS))
def test_real_data_no_selected_forecast_postdates_its_cutoff(key):
    from app import storage

    actuals, forecasts = storage.load_frames(config.DB_PATH)
    t = build_aligned_table(
        actuals, forecasts, config.DELIVERY_FROM, config.DELIVERY_TO, config.CUTOFFS[key]
    )
    used = t.dropna(subset=["forecast_publish_time"])
    assert len(used) == len(t) == 31 * 24, "every delivery hour should have a usable vintage"
    assert (used.forecast_publish_time + LAG <= used.cutoff).all(), "LOOKAHEAD LEAK"
    assert (used.forecast_publish_time < used.target_time).all(), "selected a past-dated row"
    assert (used.lead_time_h > 0).all()
    assert (t.cutoff < t.target_time).all()
