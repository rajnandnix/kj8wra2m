// Response types mirror backend/app/schemas.py (camelCase JSON).

export interface CutoffInfo {
  key: string;
  label: string;
  localTime: string;
  timezone: string;
  description: string;
  rule: string;
  publicationLagMinutes: number;
}

export interface DateWindow {
  decisionFrom: string;
  decisionTo: string;
  deliveryFrom: string;
  deliveryTo: string;
}

export interface Health {
  status: string;
  dataWindow: DateWindow;
  rowCounts: { actuals: number; forecasts: number; publications: number };
  buildTimestamp: string;
  sources: { actuals: string; forecast: string };
  cutoffs: CutoffInfo[];
  primaryCutoff: string;
  defaultDeliveryDate: string;
  largestMissDate: string;
  sensitivityExampleDate: string;
  errorDefinition: string;
}

export interface Headline {
  nExpected: number;
  nValid: number;
  nMissingForecast: number;
  nMissingActual: number;
  nMissingBoth: number;
  coveragePct: number;
  maeMw: number | null;
  rmseMw: number | null;
  biasMw: number | null;
  nmaePct: number | null;
  meanActualMw: number | null;
  meanForecastMw: number | null;
  p10Mw: number | null;
  p50Mw: number | null;
  p90Mw: number | null;
  maxAbsErrorMw: number | null;
  maxAbsErrorTime: string | null;
  debiasedMaeMw: number | null;
  debiasedRmseMw: number | null;
  meanLeadTimeH: number | null;
}

export interface BandBucket {
  bucket: string;
  fromMw: number;
  toMw: number | null;
  n: number;
  p10Mw: number | null;
  p50Mw: number | null;
  p90Mw: number | null;
  coveragePct: number | null;
  unconditionalCoveragePct: number | null;
}

export interface ProcurementBand {
  basis: string;
  conditional: boolean;
  forecastMw: number;
  windLowMw: number;
  windHighMw: number;
  coverLowMw: number;
  coverHighMw: number;
  coverP90Mw: number;
  coverP90Mwh: number;
  hours: number;
  buckets: BandBucket[];
  overallCoveragePct: number | null;
  unconditionalCoveragePct: number | null;
}

export interface ForecastPoint {
  time: string;
  forecastMw: number | null;
  actualMw: number | null;
  errorMw: number | null;
  publishTime: string | null;
  leadTimeH: number | null;
  windLowMw: number | null;
  windHighMw: number | null;
  bandBucket: string | null;
  status: string;
}

export interface CutoffDayView {
  cutoff: CutoffInfo;
  cutoffUtc: string;
  vintagePublishTimes: string[];
  maeMw: number | null;
  biasMw: number | null;
}

export interface ForecastResponse {
  deliveryDate: string;
  cutoff: CutoffInfo;
  cutoffUtc: string;
  cutoffLocal: string;
  vintagePublishTimes: string[];
  forecast: ForecastPoint[];
  actualsHalfHourly: { time: string; mw: number }[];
  dayMetrics: Headline;
  hoursInsideBand: number;
  band: ProcurementBand;
  bandWindow: DateWindow;
  otherCutoffs: CutoffDayView[];
  errorDefinition: string;
}

export interface DayRow {
  deliveryDate: string;
  nExpected: number;
  nValid: number;
  maeMw: number | null;
  rmseMw: number | null;
  biasMw: number | null;
  meanActualMw: number | null;
  maxAbsErrorMw: number | null;
}

export interface AccuracyResponse {
  cutoff: CutoffInfo;
  deliveryFrom: string;
  deliveryTo: string;
  headline: Headline;
  histogram: { fromMw: number; toMw: number; count: number }[];
  byDay: DayRow[];
  errors: { time: string; errorMw: number | null }[];
  worstDay: DayRow | null;
  worstIntervals: {
    time: string;
    forecastMw: number;
    actualMw: number;
    errorMw: number;
    absErrorMw: number;
    publishTime: string;
  }[];
  errorDefinition: string;
}

export interface HourRow {
  hour: number;
  n: number;
  maeMw: number | null;
  rmseMw: number | null;
  biasMw: number | null;
  meanActualMw: number | null;
}

export interface LevelRow {
  bucket: string;
  fromMw: number;
  toMw: number | null;
  n: number;
  maeMw: number | null;
  rmseMw: number | null;
  biasMw: number | null;
  meanActualMw: number | null;
  meanForecastMw: number | null;
  biasPctOfActual: number | null;
  biasPctOfForecast: number | null;
}

export interface LevelTrend {
  slopeMwPerMw: number | null;
  interceptMw: number | null;
  correlation: number | null;
  rSquared: number | null;
}

export interface Breakdown<R> {
  by: string;
  basis: string | null;
  cutoff: CutoffInfo;
  rows: R[];
  trend: LevelTrend | null;
}

export interface CutoffComparison {
  baseline: string;
  alternative: string;
  nPaired: number;
  maeBaselineMw: number;
  maeAlternativeMw: number;
  maeDeltaMw: number;
  maeDeltaPct: number;
  maeDeltaCi95Mw: [number, number];
  maeDeltaCi95Pct: [number, number];
  rmseDeltaMw: number;
  rmseDeltaPct: number;
  debiasedMaeDeltaMw: number;
  biasDeltaMw: number;
  shareIntervalsImprovedPct: number;
  shareDaysImprovedPct: number;
  ciIncludesZero: boolean;
  verdict: string;
}

export interface Sensitivity {
  primaryCutoff: string;
  results: { cutoff: CutoffInfo; headline: Headline; vintagePublishTimes: string[] }[];
  comparisons: CutoffComparison[];
  method: string;
}

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

async function get<T>(path: string, params: Record<string, string | undefined> = {}): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) qs.set(k, v);
  const query = qs.toString();
  const url = `${BASE}${path}${query ? `?${query}` : ""}`;
  let res: Response;
  try {
    res = await fetch(url);
  } catch {
    throw new Error("Could not reach the data service. Check your connection and retry.");
  }
  if (!res.ok) {
    let msg = `The data service returned ${res.status}.`;
    try {
      msg = (await res.json()).error?.message ?? msg;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => get<Health>("/api/health"),
  forecast: (deliveryDate: string, cutoff: string) =>
    get<ForecastResponse>("/api/forecast", { deliveryDate, cutoff }),
  accuracy: (cutoff: string) => get<AccuracyResponse>("/api/accuracy", { cutoff }),
  breakdown: <R,>(by: "hour" | "level" | "day", cutoff: string, basis?: string) =>
    get<Breakdown<R>>("/api/accuracy/breakdown", { by, cutoff, basis }),
  sensitivity: () => get<Sensitivity>("/api/sensitivity"),
};
