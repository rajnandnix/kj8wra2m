import { ErrorHistogram, ErrorSeriesChart } from "../components/charts/AccuracyCharts";
import { LeadFinding, MetricCards, SignNote } from "../components/MetricCards";
import { SensitivityPanel } from "../components/SensitivityPanel";
import { Async, Card, DataTable, Details, Grid } from "../components/ui";
import { useAccuracy } from "../hooks/useApi";
import { dayLong, mw, num, signedMw } from "../lib/format";
import s from "./Pages.module.css";

export function AccuracyPage({ cutoffKey }: { cutoffKey: string }) {
  const q = useAccuracy(cutoffKey);
  return (
    <div className={s.stack}>
      <Async query={q} height={420}>
        {(d) => (
          <>
            <LeadFinding h={d.headline} cutoffKey={d.cutoff.key} cutoffLabel={d.cutoff.localTime} />
            <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: 13.5 }}>
              {d.cutoff.label}, {d.cutoff.localTime} Europe/London on D-1. {d.cutoff.rule}
            </p>
            <SignNote />
            <MetricCards h={d.headline} />
            <Card
              title="Forecast error across every delivery day"
              sub="Each point is one hour. Spikes are locatable; the worst day by MAE is shaded."
            >
              <ErrorSeriesChart data={d} />
              <Details summary="View daily results as a table">
                <DataTable
                  head={["Delivery day", "Intervals", "MAE", "RMSE", "Bias", "Mean actual", "Worst hour"]}
                  rows={d.byDay.map((r) => [
                    dayLong(r.deliveryDate),
                    `${r.nValid} of ${r.nExpected}`,
                    mw(r.maeMw),
                    mw(r.rmseMw),
                    signedMw(r.biasMw),
                    mw(r.meanActualMw),
                    mw(r.maxAbsErrorMw),
                  ])}
                />
              </Details>
            </Card>
            <Card
              title="How errors are distributed"
              sub={`P10 ${signedMw(d.headline.p10Mw)}, median ${signedMw(d.headline.p50Mw)}, P90 ${signedMw(d.headline.p90Mw)}. The band between P10 and P90 is what the procurement band is built from.`}
            >
              <ErrorHistogram data={d} />
            </Card>
            <Grid cols={2}>
              <Card title="Constant offset versus the rest of the error" sub="Supporting evidence for the finding above, measured against FUELHH.">
                <p className={s.prose} style={{ marginTop: 0 }}>
                  Headline MAE is <b>{mw(d.headline.maeMw)}</b>, and the forecast ran <b>{mw(d.headline.biasMw)}</b> high on
                  average. Subtract that constant offset and MAE would be <b>{mw(d.headline.debiasedMaeMw)}</b> and RMSE{" "}
                  <b>{mw(d.headline.debiasedRmseMw)}</b>. Headline figures stay uncorrected because this tool evaluates the
                  forecast as published. The cross-check attributes most of the offset to the datasets covering different wind
                  fleets, so this is not evidence that a standing correction would improve the forecast.
                </p>
              </Card>
              <Card title="Worst single hour" sub="Clients remember the worst day.">
                <p className={s.prose} style={{ marginTop: 0 }}>
                  {d.worstDay ? (
                    <>
                      Worst delivery day by MAE: <b>{dayLong(d.worstDay.deliveryDate)}</b> at <b>{mw(d.worstDay.maeMw)}</b>{" "}
                      (bias {signedMw(d.worstDay.biasMw)}). Largest single-hour miss: <b>{mw(d.headline.maxAbsErrorMw)}</b>
                      . Over the window, {num(d.headline.nValid)} intervals were scored.
                    </>
                  ) : (
                    "No scored days."
                  )}
                </p>
              </Card>
            </Grid>
          </>
        )}
      </Async>
      <SensitivityPanel />
    </div>
  );
}
