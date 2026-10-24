import { useSensitivity } from "../hooks/useApi";
import type { CutoffComparison, Sensitivity } from "../lib/api";
import { dayLong, mw, num, pct, signedMw, signedPct } from "../lib/format";
import { CutoffMaeChart, DayDeltaChart } from "./charts/AccuracyCharts";
import { Async, Card, DataTable, Note, Split } from "./ui";

function ComparisonCard({ c, name }: { c: CutoffComparison; name: string }) {
  return (
    <div style={{ background: "var(--surface-2)", borderRadius: 10, padding: "14px 16px", fontSize: 13.5, lineHeight: 1.55 }}>
      <div style={{ fontWeight: 650, marginBottom: 4 }}>{name}</div>
      <div style={{ fontWeight: 600 }}>
        Better on {c.daysImproved} days, worse on {c.daysWorse}
        {c.daysUnchanged ? `, unchanged on ${c.daysUnchanged}` : ""}.
      </div>
      <div>
        MAE <b>{signedMw(c.maeDeltaMw)}</b> ({signedPct(c.maeDeltaPct)}), 95% interval {signedPct(c.maeDeltaCi95Pct[0])} to{" "}
        {signedPct(c.maeDeltaCi95Pct[1])}
      </div>
      <div>
        RMSE {signedMw(c.rmseDeltaMw)} ({signedPct(c.rmseDeltaPct)}) · debiased MAE {signedMw(c.debiasedMaeDeltaMw)} · better on{" "}
        {pct(c.shareDaysImprovedPct, 0)} of days
      </div>
      <div style={{ marginTop: 4, color: "var(--text-secondary)" }}>{c.verdict}</div>
    </div>
  );
}

function Body({ data }: { data: Sensitivity }) {
  const label = (key: string) => data.results.find((r) => r.cutoff.key === key)?.cutoff;
  const title = (key: string) => `${label(key)?.localTime} ${label(key)?.label}`;
  const chartRows = data.results.map((r) => ({
    name: `${r.cutoff.localTime} ${r.cutoff.label}`,
    mae: r.headline.maeMw ?? 0,
  }));
  const later = data.comparisons.find((c) => c.alternative === "epex30");

  return (
    <>
      {later && (
        <Note>
          <b>
            Directional, not reliable. At the {label("epex30")?.localTime} gate MAE is {pct(Math.abs(later.maeDeltaPct))}{" "}
            {later.maeDeltaMw < 0 ? "lower" : "higher"} on average ({num(Math.abs(later.maeDeltaMw))} MW), but it is better
            on {later.daysImproved} days and <u>worse on {later.daysWorse}</u>.
          </b>{" "}
          {later.bestDay && later.maeDeltaPctWithoutBestDay != null
            ? `One day carries much of the gain: without ${dayLong(later.bestDay)} the change is ${signedPct(later.maeDeltaPctWithoutBestDay)}. `
            : ""}
          {later.ciIncludesZero
            ? `The 95% interval (${signedPct(later.maeDeltaCi95Pct[0])} to ${signedPct(later.maeDeltaCi95Pct[1])}) reaches zero, so one month supports a directional case for buying later, not a reliable one.`
            : "The 95% interval excludes zero."}
        </Note>
      )}

      <Split>
        <CutoffMaeChart rows={chartRows} />
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <h3 style={{ fontSize: 14, margin: 0 }}>Each cutoff against the {label(data.primaryCutoff)?.localTime} primary</h3>
          {data.comparisons.map((c) => (
            <ComparisonCard key={c.alternative} c={c} name={`${title(c.alternative)} vs ${label(data.primaryCutoff)?.localTime}`} />
          ))}
          <p style={{ color: "var(--text-secondary)", fontSize: 12.5, margin: 0 }}>
            Negative change means the alternative is more accurate. {data.method}
          </p>
        </div>
      </Split>

      {later && (
        <>
          <h3 style={{ fontSize: 14, margin: "20px 0 4px" }}>
            Day by day: every delivery day at the {label("epex30")?.localTime} gate against {label(data.primaryCutoff)?.localTime}
          </h3>
          <p style={{ color: "var(--text-secondary)", fontSize: 12.5, margin: "0 0 8px" }}>
            The average hides days moving in both directions. Bars above zero are days that got worse.
          </p>
          <DayDeltaChart days={later.byDay} label={label("epex30")?.localTime ?? ""} />
        </>
      )}

      <h3 style={{ fontSize: 14, margin: "20px 0 8px" }}>Full metric set at every cutoff</h3>
      <DataTable
        head={["Cutoff (D-1, London)", "Vintage (UTC)", "MAE", "RMSE", "Bias", "nMAE", "P10", "P50", "P90", "Debiased MAE", "Debiased RMSE", "Coverage"]}
        rows={data.results.map((r) => [
          `${title(r.cutoff.key)}${r.cutoff.key === data.primaryCutoff ? " (primary)" : ""}`,
          r.vintagePublishTimes.join(", "),
          mw(r.headline.maeMw),
          mw(r.headline.rmseMw),
          signedMw(r.headline.biasMw),
          pct(r.headline.nmaePct),
          signedMw(r.headline.p10Mw),
          signedMw(r.headline.p50Mw),
          signedMw(r.headline.p90Mw),
          mw(r.headline.debiasedMaeMw),
          mw(r.headline.debiasedRmseMw),
          pct(r.headline.coveragePct),
        ])}
      />
    </>
  );
}

export function SensitivityPanel() {
  const q = useSensitivity();
  return (
    <Card
      title="Cutoff sensitivity: does buying later mean buying against a better forecast?"
      sub="The same metrics at each GB day-ahead gate closure. Later gates admit later WINDFOR publications."
    >
      <Async query={q} height={420}>
        {(d) => <Body data={d} />}
      </Async>
    </Card>
  );
}
