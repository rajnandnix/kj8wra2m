"""API contract tests against the committed snapshot."""

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app

pytestmark = pytest.mark.skipif(not config.DB_PATH.exists(), reason="snapshot not built")
client = TestClient(app, raise_server_exceptions=False)


def test_health_identifies_the_build_and_window():
    j = client.get("/api/health").json()
    assert j["status"] == "ok"
    assert (
        j["dataWindow"]["deliveryFrom"] == "2026-01-02"
        and j["dataWindow"]["deliveryTo"] == "2026-02-01"
    )
    assert j["rowCounts"]["actuals"] == 1488
    assert j["buildTimestamp"]
    assert [c["key"] for c in j["cutoffs"]] == ["epex60", "n2ex", "epex30"]
    assert j["primaryCutoff"] == "epex60"
    assert j["defaultDeliveryDate"] == "2026-01-09"
    assert j["sensitivityExampleDate"] == "2026-01-28"
    assert j["largestMissDate"] == "2026-01-28"


def test_forecast_echoes_the_cutoff_rule_and_never_shows_a_later_vintage():
    j = client.get("/api/forecast", params={"deliveryDate": "2026-01-15"}).json()
    assert j["cutoff"]["key"] == "epex60"
    assert j["cutoffUtc"].startswith("2026-01-14T09:20")
    assert "publishTime" in j["cutoff"]["rule"]
    assert j["vintagePublishTimes"] == ["2026-01-14T07:30:00Z"]
    assert len(j["forecast"]) == 24
    assert all(p["publishTime"] <= j["cutoffUtc"] for p in j["forecast"])
    band = j["band"]
    assert band["conditional"] is True and band["coverP90Mw"] >= 0
    assert "In-sample" in band["basis"] and "out-of-sample" in band["basis"]
    assert [b["bucket"] for b in band["buckets"]] == ["< 6 GW", "6-10 GW", "10-14 GW", ">= 14 GW"]
    assert all(70 <= b["coveragePct"] <= 90 for b in band["buckets"])  # in-sample, ~80% by design
    assert 70 <= band["overallCoveragePct"] <= 90
    assert all(p["bandBucket"] for p in j["forecast"])
    assert all(p["windLowMw"] < p["forecastMw"] for p in j["forecast"] if p["forecastMw"] > 6000)
    assert "forecast - actual" in j["errorDefinition"]


def test_forecast_at_later_cutoff_uses_a_later_vintage():
    j = client.get(
        "/api/forecast", params={"deliveryDate": "2026-01-15", "cutoff": "epex30"}
    ).json()
    assert j["vintagePublishTimes"] == ["2026-01-14T11:30:00Z"]  # not the 15:30 one on the gate


def test_accuracy_headline_and_coverage():
    j = client.get("/api/accuracy").json()
    h = j["headline"]
    assert h["nExpected"] == 744 and h["nValid"] == 744 and h["coveragePct"] == 100.0
    assert h["p10Mw"] < h["p50Mw"] < h["p90Mw"]
    assert len(j["worstIntervals"]) == 10 and len(j["errors"]) == 744
    assert j["cutoff"]["key"] == "epex60"


@pytest.mark.parametrize("by,n", [("hour", 24), ("level", 4), ("day", 31)])
def test_breakdowns(by, n):
    j = client.get("/api/accuracy/breakdown", params={"by": by}).json()
    assert len(j["rows"]) == n and j["cutoff"]["key"] == "epex60"


def test_sensitivity_has_all_cutoffs_and_paired_comparisons():
    j = client.get("/api/sensitivity").json()
    assert [r["cutoff"]["key"] for r in j["results"]] == ["epex60", "n2ex", "epex30"]
    assert [c["alternative"] for c in j["comparisons"]] == ["n2ex", "epex30"]
    assert all(c["nPaired"] == 744 and c["verdict"] for c in j["comparisons"])


@pytest.mark.parametrize(
    "path,params,status",
    [
        ("/api/forecast", {"deliveryDate": "2025-12-31"}, 400),
        ("/api/forecast", {"deliveryDate": "2026-01-15", "cutoff": "nope"}, 400),
        ("/api/forecast", {}, 422),
        ("/api/forecast", {"deliveryDate": "banana"}, 422),
        ("/api/accuracy", {"from": "2026-01-20", "to": "2026-01-10"}, 400),
        ("/api/accuracy/breakdown", {"by": "week"}, 422),
    ],
)
def test_errors_are_clean_json_never_a_stack_trace(path, params, status):
    r = client.get(path, params=params)
    assert r.status_code == status
    j = r.json()
    assert set(j["error"]) == {"code", "message"}
    assert "Traceback" not in r.text


def test_openapi_page_is_served():
    assert client.get("/api/docs").status_code == 200
    assert client.get("/api/openapi.json").status_code == 200


def test_band_is_conditional_on_forecast_level():
    """A high-forecast day needs more cover than a low one: not a single global pair."""
    hi = client.get("/api/forecast", params={"deliveryDate": "2026-01-12"}).json()["band"]  # ~19 GW
    lo = client.get("/api/forecast", params={"deliveryDate": "2026-01-19"}).json()["band"]  # ~6 GW
    assert hi["forecastMw"] > lo["forecastMw"] + 8000
    assert hi["coverP90Mw"] > lo["coverP90Mw"] + 1000


def test_sensitivity_is_cached_and_stable():
    a = client.get("/api/sensitivity").json()
    b = client.get("/api/sensitivity").json()
    assert a == b
