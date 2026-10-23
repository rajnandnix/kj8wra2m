import { useState } from "react";
import { HourChart, LevelChart } from "../components/charts/BreakdownCharts";
import { SignNote } from "../components/MetricCards";
import { Async, Card, DataTable, Details } from "../components/ui";
import { useAccuracy, useHourBreakdown, useLevelBreakdown } from "../hooks/useApi";
import { dateTimeOf, mw, num, pct, signedMw } from "../lib/format";
import s from "./Pages.module.css";

type Basis = "actual" | "forecast";

function LevelCard({ cutoffKey }: { cutoffKey: string }) {
  const [basis, setBasis] = useState<Basis>("forecast");
  const q = useLevelBreakdown(cutoffKey, basis);
  return (
    <Card
      title="Error by generation level"
      sub="Does the miss grow when there is more wind? Grouped by hourly level, in GW buckets sized for this data."
    >
      <div className={s.toggle} role="group" aria-label="Bucket by">
        <button aria-pressed={basis === "forecast"} onClick={() => setBasis("forecast")}>
          Bucket by forecast
        </button>
        <button aria-pressed={basis === "actual"} onClick={() => setBasis("actual")}>
          Bucket by actual
        </button>
      </div>
      <Async query={q} height={400}>
        {(d) => (
          <>
            <LevelChart rows={d.rows} basis={basis} />
            {d.trend?.slopeMwPerMw != null && (
              <p className={s.prose}>
                <b>
                  Across all hours, each extra 1 MW of {basis} adds {d.trend.slopeMwPerMw.toFixed(2)} MW of error; {basis}{" "}
                  level explains {pct((d.trend.rSquared ?? 0) * 100, 0)} of the error variance.
                </b>{" "}
                {basis === "forecast"
                  ? "Bucketing by forecast is what a trader can see at decision time, and it shows the bias growing with the forecast level: the pattern curtailment of wind at high output would produce, on top of a smaller offset that is present at every level."
                  : "Bucketing by realised output makes low buckets look biased high even for a noisy, unbiased forecast, because the bucket is chosen by the outcome. It is shown because it is the conventional view; the forecast view is the decision-relevant one."}
              </p>
            )}
            <Details summary="View level buckets as a table">
              <DataTable
                head={["Bucket", "Hours", "MAE", "RMSE", "Bias", "Bias % of mean actual", "Bias % of mean forecast"]}
                rows={d.rows.map((r) => [
                  r.bucket,
                  num(r.n),
                  mw(r.maeMw),
                  mw(r.rmseMw),
                  signedMw(r.biasMw),
                  pct(r.biasPctOfActual),
                  pct(r.biasPctOfForecast),
                ])}
              />
            </Details>
          </>
        )}
      </Async>
    </Card>
  );
}

export function BreakdownPage({ cutoffKey }: { cutoffKey: string }) {
  const hours = useHourBreakdown(cutoffKey);
  const acc = useAccuracy(cutoffKey);
  return (
    <div className={s.stack}>
      <SignNote />
      <Card
        title="Error by hour of day"
        sub="Mean absolute error and bias for each hour of the delivery day, across all 31 days."
      >
        <Async query={hours} height={380}>
          {(d) => (
            <>
              <HourChart rows={d.rows} />
              <Details summary="View hourly breakdown as a table">
                <DataTable
                  head={["Hour (UTC)", "Intervals", "MAE", "RMSE", "Bias"]}
                  rows={d.rows.map((r) => [
                    `${String(r.hour).padStart(2, "0")}:00`,
                    r.n,
                    mw(r.maeMw),
                    mw(r.rmseMw),
                    signedMw(r.biasMw),
                  ])}
                />
              </Details>
            </>
          )}
        </Async>
      </Card>

      <LevelCard cutoffKey={cutoffKey} />

      <Card title="Ten worst intervals" sub="Largest absolute forecast errors in the window, with the forecast vintage that was in hand.">
        <Async query={acc} height={300}>
          {(d) => (
            <DataTable
              head={["Hour starting (UTC)", "Forecast", "Actual", "Error", "Forecast published (UTC)"]}
              rows={d.worstIntervals.map((w) => [
                dateTimeOf(w.time),
                mw(w.forecastMw),
                mw(w.actualMw),
                signedMw(w.errorMw),
                dateTimeOf(w.publishTime),
              ])}
            />
          )}
        </Async>
      </Card>
    </div>
  );
}
