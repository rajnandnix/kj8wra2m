import type { Headline } from "../lib/api";
import { dateTimeOf, mw, num, pct, signedMw } from "../lib/format";
import { Card, DataTable, Grid, Metric } from "./ui";

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
          secondary="Mostly a scope difference between datasets (see the finding above)."
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

/** Fixed results of the one-off scope cross-check (scripts/scope_check.py), computed at the 09:20
 *  cutoff only. They are NOT recomputed when the cutoff selector changes, and the card says so. */
const VALIDATION_0920 = [
  { label: "FUELHH only (what this app measures against)", mae: 2039, bias: 1748, nmae: 18.1 },
  { label: "FUELHH plus NESO embedded-wind estimate", mae: 1518, bias: -731, nmae: 11.0 },
  { label: "Elexon AGWS national wind", mae: 1330, bias: -418, nmae: 9.9 },
];

/** The lead finding: the comparison was broken, not the forecast. */
export function LeadFinding({ h, cutoffKey, cutoffLabel }: { h: Headline; cutoffKey: string; cutoffLabel: string }) {
  if (h.maeMw == null || h.biasMw == null || h.debiasedMaeMw == null) return null;
  const drop = ((h.maeMw - h.debiasedMaeMw) / h.maeMw) * 100;
  const fixedToPrimary = cutoffKey === "epex60";
  return (
    <section
      aria-labelledby="lead-finding"
      style={{ border: "2px solid var(--series-1)", borderRadius: 14, background: "var(--surface-1)", padding: "22px 26px", display: "flex", flexDirection: "column", gap: 12 }}
    >
      <div style={{ color: "var(--accent)", fontSize: 12, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>
        The finding
      </div>
      <h2 id="lead-finding" style={{ fontSize: 22, lineHeight: 1.4, fontWeight: 600, margin: 0, maxWidth: "70ch" }}>
        We checked whether the forecast was broken, and found the comparison was broken instead.
      </h2>
      <p style={{ margin: 0, fontSize: 16, lineHeight: 1.55, maxWidth: "90ch" }}>
        Measured against FUELHH, day-ahead error at the {cutoffLabel} gate is about <b>{mw(h.maeMw)}</b>, roughly{" "}
        <b>{pct(h.nmaePct, 0)}</b> of mean output. <b>That is misleading.</b> Most of the gap is that WINDFOR and FUELHH count
        different wind fleets. Against a fleet-matched outturn, the same forecast at the 09:20 gate is off by about{" "}
        <b>1,330 MW, roughly 10%</b>.
      </p>
      <p style={{ margin: 0, fontSize: 16, lineHeight: 1.55, fontWeight: 600, maxWidth: "90ch" }}>
        For the desk: confirm which outturn series your position settles against. Benchmarking against the wrong one would
        have you applying a 1.7 GW standing correction you do not need.
      </p>

      <div style={{ background: "var(--surface-2)", borderRadius: 10, padding: "14px 16px", fontSize: 13.5, lineHeight: 1.55 }}>
        <b>Evidence: the same 09:20 day-ahead forecast against three definitions of &ldquo;actual wind&rdquo;</b>{" "}
        <span style={{ color: "var(--text-secondary)" }}>
          (fixed results from a one-off cross-check at the 09:20 gate; they do not change with the cutoff selector)
        </span>
        <DataTable
          head={["Outturn series", "MAE", "Bias", "nMAE"]}
          rows={VALIDATION_0920.map((r) => [r.label, mw(r.mae), signedMw(r.bias), pct(r.nmae)])}
        />
        <p style={{ margin: "8px 0 0", color: "var(--text-secondary)" }}>
          The forecast covers wind that FUELHH (transmission-metered) leaves out, chiefly embedded wind, which NESO estimates
          at about 2.5 GW on average over the window. Against the two fuller series the bias is small and negative, not
          +1.7 GW. These series are the closest available match, not a perfect one. They come from a standalone script
          (<code>scripts/scope_check.py</code>), not from this application.
        </p>
      </div>

      <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: 13.5, lineHeight: 1.55, maxWidth: "100ch" }}>
        <b style={{ color: "var(--text-primary)" }}>Supporting numbers, against FUELHH at the {cutoffLabel} gate:</b> the
        forecast ran {signedMw(h.biasMw)} high on average; remove that offset and MAE falls from {mw(h.maeMw)} to{" "}
        {mw(h.debiasedMaeMw)} ({pct(drop, 0)} lower). These are two measured figures, not an additive split. That gain is the
        scope difference showing up, not forecasting skill: against the two fuller series the same step improves MAE by only
        roughly 3% to 9% (09:20 results). It is also estimated on the month it is scored on.
        {!fixedToPrimary && " The evidence table above is fixed to the 09:20 gate and does not follow the selector."}
      </p>
    </section>
  );
}
