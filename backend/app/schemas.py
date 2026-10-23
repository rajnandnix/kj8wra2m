"""Response models. JSON uses camelCase; Python uses snake_case."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ErrorBody(Model):
    code: str
    message: str


class ErrorResponse(Model):
    error: ErrorBody


class CutoffInfo(Model):
    """The decision-cutoff rule that produced a number. Echoed on every response that uses one."""

    key: str
    label: str
    local_time: str
    timezone: str
    description: str
    rule: str
    publication_lag_minutes: float


class DateWindow(Model):
    decision_from: date
    decision_to: date
    delivery_from: date
    delivery_to: date


class RowCounts(Model):
    actuals: int
    forecasts: int
    publications: int


class HealthResponse(Model):
    status: str
    data_window: DateWindow
    row_counts: RowCounts
    build_timestamp: str
    sources: dict[str, str]
    cutoffs: list[CutoffInfo]
    primary_cutoff: str
    default_delivery_date: date
    error_definition: str


class Headline(Model):
    n_expected: int
    n_valid: int
    n_missing_forecast: int
    n_missing_actual: int
    n_missing_both: int
    coverage_pct: float
    mae_mw: float | None
    rmse_mw: float | None
    bias_mw: float | None
    nmae_pct: float | None
    mean_actual_mw: float | None
    mean_forecast_mw: float | None
    p10_mw: float | None
    p50_mw: float | None
    p90_mw: float | None
    max_abs_error_mw: float | None
    max_abs_error_time: datetime | None
    debiased_mae_mw: float | None
    debiased_rmse_mw: float | None
    mean_lead_time_h: float | None


class ProcurementBand(Model):
    """Empirical band from the error quantiles of the whole window, applied to one forecast."""

    basis: str
    forecast_mw: float
    wind_low_mw: float
    wind_high_mw: float
    cover_low_mw: float
    cover_high_mw: float
    cover_p90_mw: float
    cover_p90_mwh: float
    hours: float
    p10_error_mw: float
    p90_error_mw: float


class ForecastPoint(Model):
    time: datetime
    forecast_mw: float | None
    actual_mw: float | None
    error_mw: float | None
    publish_time: datetime | None
    lead_time_h: float | None
    wind_low_mw: float | None
    wind_high_mw: float | None
    status: str


class ActualPoint(Model):
    time: datetime
    mw: float


class CutoffDayView(Model):
    cutoff: CutoffInfo
    cutoff_utc: datetime
    vintage_publish_times: list[datetime]
    mae_mw: float | None
    bias_mw: float | None


class ForecastResponse(Model):
    delivery_date: date
    cutoff: CutoffInfo
    cutoff_utc: datetime
    cutoff_local: str
    vintage_publish_times: list[datetime]
    forecast: list[ForecastPoint]
    actuals_half_hourly: list[ActualPoint]
    day_metrics: Headline
    hours_inside_band: int
    band: ProcurementBand
    band_window: DateWindow
    other_cutoffs: list[CutoffDayView]
    error_definition: str


class ErrorPoint(Model):
    time: datetime
    error_mw: float | None


class DayRow(Model):
    delivery_date: date
    n_expected: int
    n_valid: int
    mae_mw: float | None
    rmse_mw: float | None
    bias_mw: float | None
    mean_actual_mw: float | None
    max_abs_error_mw: float | None


class HistogramBin(Model):
    from_mw: float
    to_mw: float
    count: int


class WorstInterval(Model):
    time: datetime
    forecast_mw: float
    actual_mw: float
    error_mw: float
    abs_error_mw: float
    publish_time: datetime


class AccuracyResponse(Model):
    cutoff: CutoffInfo
    delivery_from: date
    delivery_to: date
    headline: Headline
    histogram: list[HistogramBin]
    by_day: list[DayRow]
    errors: list[ErrorPoint]
    worst_day: DayRow | None
    worst_intervals: list[WorstInterval]
    error_definition: str


class HourRow(Model):
    hour: int
    n: int
    mae_mw: float | None
    rmse_mw: float | None
    bias_mw: float | None
    mean_actual_mw: float | None


class LevelRow(Model):
    bucket: str
    from_mw: float
    to_mw: float | None
    n: int
    mae_mw: float | None
    rmse_mw: float | None
    bias_mw: float | None
    mean_actual_mw: float | None
    mean_forecast_mw: float | None
    bias_pct_of_actual: float | None
    bias_pct_of_forecast: float | None


class LevelTrend(Model):
    slope_mw_per_mw: float | None
    intercept_mw: float | None
    correlation: float | None
    r_squared: float | None


class BreakdownResponse(Model):
    by: str
    basis: str | None
    cutoff: CutoffInfo
    delivery_from: date
    delivery_to: date
    rows: list[HourRow | LevelRow | DayRow]
    trend: LevelTrend | None
    error_definition: str


class CutoffResult(Model):
    cutoff: CutoffInfo
    headline: Headline
    vintage_publish_times: list[str]


class CutoffComparison(Model):
    """Alternative cutoff against the baseline, on intervals valid under both. Delta is
    alternative minus baseline, so a negative delta means the alternative is more accurate."""

    baseline: str
    alternative: str
    n_paired: int
    mae_baseline_mw: float
    mae_alternative_mw: float
    mae_delta_mw: float
    mae_delta_pct: float
    mae_delta_ci95_mw: tuple[float, float]
    mae_delta_ci95_pct: tuple[float, float]
    rmse_delta_mw: float
    rmse_delta_pct: float
    debiased_mae_delta_mw: float
    bias_delta_mw: float
    share_intervals_improved_pct: float
    share_days_improved_pct: float
    ci_includes_zero: bool
    verdict: str


class SensitivityResponse(Model):
    delivery_from: date
    delivery_to: date
    primary_cutoff: str
    results: list[CutoffResult]
    comparisons: list[CutoffComparison]
    method: str
    error_definition: str
