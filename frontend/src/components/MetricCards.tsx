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

/** The lead finding: two measured figures with the systematic offset named. Deliberately not an
 *  additive decomposition (MAE does not split into bias plus a remainder). */
export function LeadFinding({ h, cutoffLabel }: { h: Headline; cutoffLabel: string }) {
  if (h.maeMw == null || h.biasMw == null || h.debiasedMaeMw == null) return null;
  const drop = ((h.maeMw - h.debiasedMaeMw) / h.maeMw) * 100;
  return (
    <section
      aria-labelledby="lead-finding"
      style={{ border: "2px solid var(--series-1)", borderRadius: 14, background: "var(--surface-1)", padding: "22px 26px", display: "flex", flexDirection: "column", gap: 12 }}
    >
      <div style={{ color: "var(--accent)", fontSize: 12, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>
        The finding, {cutoffLabel}
      </div>
      <h2 id="lead-finding" style={{ fontSize: 22, lineHeight: 1.4, fontWeight: 500, margin: 0, maxWidth: "62ch" }}>
        MAE <b>{mw(h.maeMw)}</b>, with the forecast running <b>{signedMw(h.biasMw)}</b> high on average. Remove that systematic
        offset and MAE falls to <b>{mw(h.debiasedMaeMw)}</b>.
      </h2>
      <p style={{ margin: 0, fontSize: 17, fontWeight: 600 }}>
        Apply a standing correction and your typical miss drops by about a third ({pct(drop, 0)} lower).
      </p>
      <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: 13.5, lineHeight: 1.55, maxWidth: "100ch" }}>
        These are two measured figures, not an additive split: MAE does not decompose into bias plus a remainder. The
        correction here is estimated on the same month it is scored on, so it is an in-sample figure; one month cannot show
        it would hold in other seasons.
      </p>
      <div style={{ background: "var(--surface-2)", borderRadius: 10, padding: "12px 16px", fontSize: 13.5, lineHeight: 1.55 }}>
        <b>Where the offset comes from: scope, not forecasting skill.</b> The forecast (WINDFOR) covers wind that the metered
        outturn series (FUELHH) leaves out, chiefly embedded, distribution-connected wind. Checked against independent
        sources at the 09:20 cutoff: NESO&apos;s embedded-wind estimate averages 2,479 MW over the window, and against
        full-fleet outturn the day-ahead MAE is about <b>1,330 to 1,520 MW (10 to 11% of mean output)</b> with the bias
        shrinking to about −0.4 to −0.7 GW. So the correction is largely a reconciliation between two datasets: confirm
        which series your position is actually measured against before applying it.
      </div>
    </section>
  );
}
