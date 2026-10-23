import type { Headline } from "../lib/api";
import { dateTimeOf, mw, num, pct, signedMw } from "../lib/format";
import { Card, Grid, Metric } from "./ui";

export function MetricCards({ h }: { h: Headline }) {
  const excluded = h.nExpected - h.nValid;
  return (
    <>
      <Grid cols={5}>
        <Metric
          label="Mean absolute error (MAE)"
          value={num(h.maeMw)}
          unit="MW"
          note="Typical size of a miss, either direction."
          secondary={<>Debiased MAE: {mw(h.debiasedMaeMw)}</>}
        />
        <Metric
          label="Root mean square error (RMSE)"
          value={num(h.rmseMw)}
          unit="MW"
          note="Penalises large misses; higher than MAE when errors are spiky."
          secondary={<>Debiased RMSE: {mw(h.debiasedRmseMw)}</>}
        />
        <Metric
          label="Bias (mean error)"
          value={signedMw(h.biasMw).replace(" MW", "")}
          unit="MW"
          note={
            h.biasMw != null && h.biasMw > 0
              ? "Forecast ran high on average: systematic under-procurement."
              : "Forecast ran low on average: systematic over-procurement."
          }
          secondary="A standing offset a correction could remove."
        />
        <Metric
          label="Normalised MAE (nMAE)"
          value={pct(h.nmaePct)}
          note={`MAE divided by mean actual output (${mw(h.meanActualMw)}).`}
        />
        <Metric
          label="Data coverage"
          value={pct(h.coveragePct)}
          note={`${num(h.nValid)} of ${num(h.nExpected)} hourly intervals have both a forecast and an actual.`}
          secondary={
            excluded === 0
              ? "No intervals excluded."
              : `${excluded} excluded: ${h.nMissingForecast} no forecast, ${h.nMissingActual} no actual, ${h.nMissingBoth} neither.`
          }
        />
      </Grid>
      <Grid cols={3}>
        <Metric label="P10 of error" value={signedMw(h.p10Mw).replace(" MW", "")} unit="MW" note="1 in 10 hours the forecast was this far below actual or lower." />
        <Metric label="P50 of error (median)" value={signedMw(h.p50Mw).replace(" MW", "")} unit="MW" note="Half of all hours were above this." />
        <Metric
          label="P90 of error"
          value={signedMw(h.p90Mw).replace(" MW", "")}
          unit="MW"
          note="1 in 10 hours the forecast exceeded actual by this much or more: the cover to hold."
          secondary={
            h.maxAbsErrorMw != null && h.maxAbsErrorTime ? (
              <>
                Worst single hour: {mw(h.maxAbsErrorMw)} on {dateTimeOf(h.maxAbsErrorTime)} UTC
              </>
            ) : undefined
          }
        />
      </Grid>
    </>
  );
}

export const SignNote = () => (
  <Card style={{ padding: "12px 18px" }}>
    <p style={{ margin: 0, fontSize: 13.5, color: "var(--text-secondary)" }}>
      <b style={{ color: "var(--text-primary)" }}>Sign convention.</b> Error = forecast − actual. A positive error means the
      forecast exceeded what was generated, so the day-ahead position was <b>under-procured</b> and the shortfall had to be
      covered later at higher cost. A negative error means over-procurement.
    </p>
  </Card>
);
