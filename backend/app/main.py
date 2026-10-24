"""FastAPI app. Read-only: analytics are computed from the committed SQLite snapshot."""

import logging
import os
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import align, config, metrics, schemas, storage

log = logging.getLogger("wind")
ERROR_DEFINITION = (
    "error = forecast - actual. Positive means the forecast was too high, so the day-ahead "
    "position was under-procured and the shortfall must be covered in a later market."
)


# --- data ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Data:
    actuals: pd.DataFrame
    forecasts: pd.DataFrame
    meta: dict[str, str]
    tables: dict[str, pd.DataFrame]  # aligned table per cutoff key
    bands: dict[str, tuple[pd.DataFrame, dict]]  # per cutoff: forecast-level quantiles, summary
    largest_miss_date: date


@lru_cache(maxsize=1)
def get_data() -> Data:
    """Load the snapshot once (read-only connection) and align it at every configured cutoff."""
    actuals, forecasts = storage.load_frames(config.DB_PATH)
    meta = storage.load_meta(config.DB_PATH)
    tables = {
        key: align.build_aligned_table(
            actuals, forecasts, config.DELIVERY_FROM, config.DELIVERY_TO, cutoff
        )
        for key, cutoff in config.CUTOFFS.items()
    }
    bands = {
        key: (metrics.conditional_error_quantiles(t), metrics.conditional_band_summary(t))
        for key, t in tables.items()
    }
    days = metrics.by_day(tables[config.PRIMARY_CUTOFF]).dropna(subset=["mae_mw"])
    largest = days.loc[days["mae_mw"].idxmax(), "delivery_date"]
    return Data(actuals, forecasts, meta, tables, bands, largest)


# --- helpers ------------------------------------------------------------------------------------


def cutoff_info(c: config.Cutoff) -> schemas.CutoffInfo:
    lag = config.PUBLICATION_LAG.total_seconds() / 60
    return schemas.CutoffInfo(
        key=c.key,
        label=c.label,
        local_time=f"{c.local_time:%H:%M}",
        timezone="Europe/London",
        description=c.description,
        rule=(
            f"For each delivery interval on day D, use the latest WINDFOR publication with "
            f"publishTime + {lag:g} min <= {c.local_time:%H:%M} Europe/London on D-1. "
            f"Nothing published later is ever used."
        ),
        publication_lag_minutes=lag,
    )


def resolve_cutoff(key: str | None) -> config.Cutoff:
    try:
        return config.cutoff_by_key(key)
    except KeyError as exc:
        raise HTTPException(400, str(exc.args[0])) from exc


def resolve_range(from_: date | None, to: date | None) -> tuple[date, date]:
    lo, hi = from_ or config.DELIVERY_FROM, to or config.DELIVERY_TO
    if lo > hi:
        raise HTTPException(400, "'from' must not be after 'to'")
    if lo < config.DELIVERY_FROM or hi > config.DELIVERY_TO:
        raise HTTPException(
            400,
            f"dates must be delivery days within {config.DELIVERY_FROM} to {config.DELIVERY_TO}",
        )
    return lo, hi


def window_of(table: pd.DataFrame, lo: date, hi: date) -> pd.DataFrame:
    return table[(table["delivery_date"] >= lo) & (table["delivery_date"] <= hi)]


def clean(v: Any) -> Any:
    """NaN / NaT to None so rows serialise as JSON null."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def records(df: pd.DataFrame) -> list[dict]:
    return [{k: clean(v) for k, v in row.items()} for row in df.to_dict("records")]


def headline_model(df: pd.DataFrame) -> schemas.Headline:
    return schemas.Headline(**metrics.headline(df))


def data_window() -> schemas.DateWindow:
    return schemas.DateWindow(
        decision_from=config.DECISION_FROM,
        decision_to=config.DECISION_TO,
        delivery_from=config.DELIVERY_FROM,
        delivery_to=config.DELIVERY_TO,
    )


# --- app ----------------------------------------------------------------------------------------

app = FastAPI(
    title="GB wind forecast accuracy",
    description=(
        "Decision-time wind forecast (Elexon WINDFOR) against metered outturn (Elexon FUELHH) "
        "for GB day-ahead purchasing. Every number depends on a decision cutoff, which each "
        "response echoes. " + ERROR_DEFINITION
    ),
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get(
        "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
    ).split(","),
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _err(status: int, code: str, message: str) -> JSONResponse:
    body = schemas.ErrorResponse(error=schemas.ErrorBody(code=code, message=message))
    return JSONResponse(status_code=status, content=body.model_dump(by_alias=True))


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
    return _err(
        exc.status_code, "bad_request" if exc.status_code < 500 else "error", str(exc.detail)
    )


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0]
    where = ".".join(str(p) for p in first["loc"] if p != "query")
    return _err(422, "invalid_parameter", f"{where}: {first['msg']}")


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error")  # detail goes to the server log, never to the client
    return _err(500, "internal_error", "Something went wrong computing this response.")


ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"model": schemas.ErrorResponse},
    422: {"model": schemas.ErrorResponse},
}


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"service": "wind-forecast-accuracy", "docs": "/api/docs", "health": "/api/health"}


@app.get("/api/health", response_model=schemas.HealthResponse, responses=ERRORS)
def health() -> schemas.HealthResponse:
    d = get_data()
    return schemas.HealthResponse(
        status="ok",
        data_window=data_window(),
        row_counts=schemas.RowCounts(
            actuals=int(d.meta["actuals_rows"]),
            forecasts=int(d.meta["forecast_rows"]),
            publications=int(d.meta["forecast_publications"]),
        ),
        build_timestamp=d.meta["build_timestamp_utc"],
        sources={"actuals": d.meta["source_fuelhh"], "forecast": d.meta["source_windfor"]},
        cutoffs=[cutoff_info(c) for c in config.CUTOFFS.values()],
        primary_cutoff=config.PRIMARY_CUTOFF,
        default_delivery_date=config.DEFAULT_DELIVERY_DATE,
        largest_miss_date=d.largest_miss_date,
        sensitivity_example_date=config.SENSITIVITY_EXAMPLE_DATE,
        error_definition=ERROR_DEFINITION,
    )


@app.get("/api/forecast", response_model=schemas.ForecastResponse, responses=ERRORS)
def forecast(
    delivery_date: date = Query(alias="deliveryDate", description="Delivery day D, YYYY-MM-DD"),
    cutoff: str | None = Query(None, description="Cutoff key; default is the primary cutoff"),
) -> schemas.ForecastResponse:
    """The forecast that was actually available at the decision cutoff, plus the outturn."""
    if not config.DELIVERY_FROM <= delivery_date <= config.DELIVERY_TO:
        raise HTTPException(
            400, f"deliveryDate must be within {config.DELIVERY_FROM} to {config.DELIVERY_TO}"
        )
    c = resolve_cutoff(cutoff)
    d = get_data()
    full = d.tables[c.key]
    day = full[full["delivery_date"] == delivery_date]
    cutoff_utc = align.decision_cutoff(delivery_date, c)

    table, summary = d.bands[c.key]
    day_head = metrics.headline(day)
    hourly = metrics.apply_conditional_band(day["forecast_mw"], table)
    day_band = metrics.day_band(day["forecast_mw"], table)

    points, inside = [], 0
    for r, (_, b) in zip(day.itertuples(), hourly.iterrows(), strict=True):
        lo = clean(b["wind_low_mw"])
        hi = clean(b["wind_high_mw"])
        if lo is not None and pd.notna(r.actual_mw) and lo <= r.actual_mw <= hi:
            inside += 1
        points.append(
            schemas.ForecastPoint(
                time=r.target_time,
                forecast_mw=clean(r.forecast_mw),
                actual_mw=clean(r.actual_mw),
                error_mw=clean(r.error),
                publish_time=clean(r.forecast_publish_time),
                lead_time_h=clean(r.lead_time_h),
                wind_low_mw=lo,
                wind_high_mw=hi,
                band_bucket=clean(b["bucket"]),
                status=r.status,
            )
        )

    lo_t = pd.Timestamp(delivery_date, tz=config.LONDON).tz_convert("UTC")
    hi_t = pd.Timestamp(delivery_date + timedelta(days=1), tz=config.LONDON).tz_convert("UTC")
    halves = d.actuals[(d.actuals["start_time"] >= lo_t) & (d.actuals["start_time"] < hi_t)]

    others = []
    for key, other in config.CUTOFFS.items():
        o = d.tables[key][d.tables[key]["delivery_date"] == delivery_date]
        oh = metrics.headline(o)
        others.append(
            schemas.CutoffDayView(
                cutoff=cutoff_info(other),
                cutoff_utc=align.decision_cutoff(delivery_date, other),
                vintage_publish_times=sorted(o["forecast_publish_time"].dropna().unique()),
                mae_mw=oh["mae_mw"],
                bias_mw=oh["bias_mw"],
            )
        )

    return schemas.ForecastResponse(
        delivery_date=delivery_date,
        cutoff=cutoff_info(c),
        cutoff_utc=cutoff_utc,
        cutoff_local=f"{c.local_time:%H:%M} Europe/London on {delivery_date - timedelta(days=1)}",
        vintage_publish_times=sorted(day["forecast_publish_time"].dropna().unique()),
        forecast=points,
        actuals_half_hourly=[
            schemas.ActualPoint(time=r.start_time, mw=r.generation_mw) for r in halves.itertuples()
        ],
        day_metrics=schemas.Headline(**day_head),
        hours_inside_band=inside,
        band=schemas.ProcurementBand(
            basis=(
                f"Each hour uses the P10 and P90 of forecast error for hours with a similar "
                f"forecast "
                f"level, from all {summary['n']} hourly intervals, {config.DELIVERY_FROM} to "
                f"{config.DELIVERY_TO}, at the {c.local_time:%H:%M} cutoff. In-sample: the band is "
                f"fitted and scored on the same month, including the day shown. One month cannot "
                f"support out-of-sample validation, so coverage in other periods is unknown and "
                f"likely lower. Not a probabilistic forecast."
            ),
            conditional=True,
            buckets=[schemas.BandBucket(**b) for b in summary["buckets"]],
            overall_coverage_pct=summary["overall_coverage_pct"],
            unconditional_coverage_pct=summary["unconditional_coverage_pct"],
            **day_band,
        ),
        band_window=data_window(),
        other_cutoffs=others,
        error_definition=ERROR_DEFINITION,
    )


@app.get("/api/accuracy", response_model=schemas.AccuracyResponse, responses=ERRORS)
def accuracy(
    from_: date | None = Query(None, alias="from", description="First delivery day"),
    to: date | None = Query(None, description="Last delivery day"),
    cutoff: str | None = Query(None),
) -> schemas.AccuracyResponse:
    """Headline metrics, error percentiles, error histogram and error time series."""
    lo, hi = resolve_range(from_, to)
    c = resolve_cutoff(cutoff)
    t = window_of(get_data().tables[c.key], lo, hi)
    days = metrics.by_day(t)
    scored = days.dropna(subset=["mae_mw"])
    worst = (
        schemas.DayRow(**{k: clean(v) for k, v in scored.loc[scored["mae_mw"].idxmax()].items()})
        if len(scored)
        else None
    )
    return schemas.AccuracyResponse(
        cutoff=cutoff_info(c),
        delivery_from=lo,
        delivery_to=hi,
        headline=headline_model(t),
        histogram=[schemas.HistogramBin(**b) for b in metrics.histogram(t)],
        by_day=[schemas.DayRow(**r) for r in records(days)],
        errors=[
            schemas.ErrorPoint(time=r.target_time, error_mw=clean(r.error)) for r in t.itertuples()
        ],
        worst_day=worst,
        worst_intervals=[
            schemas.WorstInterval(
                time=r.target_time,
                forecast_mw=r.forecast_mw,
                actual_mw=r.actual_mw,
                error_mw=r.error,
                abs_error_mw=r.abs_error,
                publish_time=r.forecast_publish_time,
            )
            for r in metrics.worst_intervals(t, 10).itertuples()
        ],
        large_miss_mw=config.LARGE_MISS_MW,
        error_definition=ERROR_DEFINITION,
    )


@app.get("/api/accuracy/breakdown", response_model=schemas.BreakdownResponse, responses=ERRORS)
def breakdown(
    by: str = Query(pattern="^(hour|level|day)$", description="hour, level or day"),
    basis: str = Query("actual", pattern="^(actual|forecast)$", description="level only"),
    from_: date | None = Query(None, alias="from"),
    to: date | None = Query(None),
    cutoff: str | None = Query(None),
) -> schemas.BreakdownResponse:
    """Error grouped by hour of day, by generation level bucket, or by delivery day."""
    lo, hi = resolve_range(from_, to)
    c = resolve_cutoff(cutoff)
    t = window_of(get_data().tables[c.key], lo, hi)
    trend = None
    if by == "hour":
        rows: list = [schemas.HourRow(**r) for r in records(metrics.by_hour(t))]
    elif by == "level":
        rows = [schemas.LevelRow(**r) for r in records(metrics.by_level(t, basis=basis))]
        trend = schemas.LevelTrend(**metrics.level_trend(t, basis=basis))
    else:
        rows = [schemas.DayRow(**r) for r in records(metrics.by_day(t))]
    return schemas.BreakdownResponse(
        by=by,
        basis=basis if by == "level" else None,
        cutoff=cutoff_info(c),
        delivery_from=lo,
        delivery_to=hi,
        rows=rows,
        trend=trend,
        error_definition=ERROR_DEFINITION,
    )


def _verdict(cmp: dict, days: dict) -> tuple[bool, str]:
    """Plain-language verdict. A pooled gain is never reported without the day-level split."""
    lo, hi = cmp["mae_delta_ci95_pct"]
    includes_zero = lo <= 0 <= hi
    pct = cmp["mae_delta_pct"]
    split = f"better on {days['days_improved']} days, worse on {days['days_worse']}" + (
        f", unchanged on {days['days_unchanged']}" if days["days_unchanged"] else ""
    )
    if abs(pct) < 3:
        return includes_zero, f"No material difference in accuracy ({split})."
    direction = "better" if pct < 0 else "worse"
    wo = days["mae_delta_pct_without_best_day"]
    without = (
        f" Without the single most-improved day the change is {wo:+.1f}%." if wo is not None else ""
    )
    if includes_zero:
        return True, (
            f"Directional, not reliable: {abs(pct):.1f}% {direction} on average, but {split}, "
            f"and the 95% interval includes zero.{without}"
        )
    return False, (
        f"Materially {direction}: {abs(pct):.1f}% MAE ({split}); "
        f"the 95% interval excludes zero.{without}"
    )


@app.get("/api/sensitivity", response_model=schemas.SensitivityResponse, responses=ERRORS)
def sensitivity(
    from_: date | None = Query(None, alias="from"), to: date | None = Query(None)
) -> schemas.SensitivityResponse:
    """The full metric set at every configured cutoff, and each against the primary cutoff."""
    lo, hi = resolve_range(from_, to)
    return _sensitivity(lo, hi)


@lru_cache(maxsize=16)
def _sensitivity(lo: date, hi: date) -> schemas.SensitivityResponse:
    d = get_data()
    wins = {k: window_of(t, lo, hi) for k, t in d.tables.items()}
    results = [
        schemas.CutoffResult(
            cutoff=cutoff_info(c),
            headline=headline_model(wins[k]),
            vintage_publish_times=sorted(
                wins[k]["forecast_publish_time"].dropna().dt.strftime("%H:%M").unique()
            ),
        )
        for k, c in config.CUTOFFS.items()
    ]
    comparisons = []
    for k in config.CUTOFFS:
        if k == config.PRIMARY_CUTOFF:
            continue
        cmp = metrics.compare_cutoffs(wins[config.PRIMARY_CUTOFF], wins[k])
        days = metrics.day_comparison(wins[config.PRIMARY_CUTOFF], wins[k])
        includes_zero, verdict = _verdict(cmp, days)
        comparisons.append(
            schemas.CutoffComparison(
                baseline=config.PRIMARY_CUTOFF,
                alternative=k,
                n_paired=cmp["n_paired"],
                mae_baseline_mw=cmp["mae_a_mw"],
                mae_alternative_mw=cmp["mae_b_mw"],
                mae_delta_mw=cmp["mae_delta_mw"],
                mae_delta_pct=cmp["mae_delta_pct"],
                mae_delta_ci95_mw=cmp["mae_delta_ci95_mw"],
                mae_delta_ci95_pct=cmp["mae_delta_ci95_pct"],
                rmse_delta_mw=cmp["rmse_delta_mw"],
                rmse_delta_pct=cmp["rmse_delta_pct"],
                debiased_mae_delta_mw=cmp["debiased_mae_delta_mw"],
                bias_delta_mw=cmp["bias_delta_mw"],
                share_intervals_improved_pct=cmp["share_intervals_improved_pct"],
                share_days_improved_pct=cmp["share_days_improved_pct"],
                ci_includes_zero=includes_zero,
                days_improved=days["days_improved"],
                days_worse=days["days_worse"],
                days_unchanged=days["days_unchanged"],
                best_day=days["best_day"],
                mae_delta_pct_without_best_day=days["mae_delta_pct_without_best_day"],
                by_day=[schemas.DayDelta(**r) for r in days["by_day"]],
                verdict=verdict,
            )
        )
    return schemas.SensitivityResponse(
        delivery_from=lo,
        delivery_to=hi,
        primary_cutoff=config.PRIMARY_CUTOFF,
        results=results,
        comparisons=comparisons,
        method=(
            f"Paired on intervals valid under both cutoffs. 95% interval: day-block bootstrap, "
            f"{config.BOOTSTRAP_RESAMPLES} resamples of whole delivery days, seed "
            f"{config.BOOTSTRAP_SEED}."
        ),
        error_definition=ERROR_DEFINITION,
    )
