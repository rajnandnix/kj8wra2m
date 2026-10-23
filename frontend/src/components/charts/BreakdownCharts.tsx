import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { HourRow, LevelRow } from "../../lib/api";
import { mw, num, pct, signedMw } from "../../lib/format";
import { Legend } from "../ui";
import { AXIS_LINE, ChartFrame, GRID, SERIES_1, SERIES_2, TICK, TooltipBox, xLabel, yAxisProps } from "./common";

const LEGEND = [
  { label: "Mean absolute error (MAE)", color: SERIES_1, kind: "box" as const },
  { label: "Bias: mean of forecast − actual (above zero = forecast too high)", color: SERIES_2, kind: "line" as const },
];

const dot = { r: 4, fill: SERIES_2, stroke: "var(--surface-1)", strokeWidth: 2 };
const activeDot = { r: 5, stroke: "var(--surface-1)", strokeWidth: 2 };

export function HourChart({ rows }: { rows: HourRow[] }) {
  return (
    <>
      <ChartFrame label="Forecast error by hour of the delivery day: MAE bars and bias line in MW">
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={rows} margin={{ top: 12, right: 16, bottom: 22, left: 4 }}>
            <CartesianGrid {...GRID} />
            <XAxis
              dataKey="hour"
              tick={TICK}
              axisLine={AXIS_LINE}
              tickLine={false}
              tickFormatter={(h: number) => String(h).padStart(2, "0")}
              label={xLabel("Hour of delivery day, starting (UTC)")}
            />
            <YAxis {...yAxisProps("Error (MW)")} />
            <Tooltip
              cursor={{ fill: "var(--surface-2)" }}
              content={({ payload }) => {
                if (!payload?.length) return null;
                const r = payload[0].payload as HourRow;
                return (
                  <TooltipBox
                    title={`${String(r.hour).padStart(2, "0")}:00 to ${String(r.hour + 1).padStart(2, "0")}:00`}
                    rows={[
                      { label: "MAE", value: mw(r.maeMw), color: SERIES_1 },
                      { label: "Bias", value: signedMw(r.biasMw), color: SERIES_2 },
                      { label: "RMSE", value: mw(r.rmseMw) },
                      { label: "Intervals", value: String(r.n) },
                    ]}
                  />
                );
              }}
            />
            <ReferenceLine y={0} stroke="var(--text-muted)" />
            <Bar dataKey="maeMw" fill={SERIES_1} barSize={16} radius={[4, 4, 0, 0]} isAnimationActive={false} />
            <Line dataKey="biasMw" stroke={SERIES_2} strokeWidth={2} dot={dot} activeDot={activeDot} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartFrame>
      <Legend items={LEGEND} />
    </>
  );
}

export function LevelChart({ rows, basis }: { rows: LevelRow[]; basis: "actual" | "forecast" }) {
  const what = basis === "actual" ? "actual outturn" : "forecast";
  return (
    <>
      <ChartFrame label={`Forecast error by ${what} level bucket: MAE bars and bias line in MW`}>
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={rows} margin={{ top: 12, right: 16, bottom: 22, left: 4 }}>
            <CartesianGrid {...GRID} />
            <XAxis
              dataKey="bucket"
              tick={TICK}
              axisLine={AXIS_LINE}
              tickLine={false}
              label={xLabel(`Hourly ${what} level`)}
            />
            <YAxis {...yAxisProps("Error (MW)")} />
            <Tooltip
              cursor={{ fill: "var(--surface-2)" }}
              content={({ payload }) => {
                if (!payload?.length) return null;
                const r = payload[0].payload as LevelRow;
                return (
                  <TooltipBox
                    title={`${r.bucket} (${what})`}
                    rows={[
                      { label: "MAE", value: mw(r.maeMw), color: SERIES_1 },
                      { label: "Bias", value: signedMw(r.biasMw), color: SERIES_2 },
                      { label: "Bias as % of mean " + (basis === "actual" ? "actual" : "forecast"), value: pct(basis === "actual" ? r.biasPctOfActual : r.biasPctOfForecast) },
                      { label: "Intervals", value: num(r.n) },
                    ]}
                  />
                );
              }}
            />
            <ReferenceLine y={0} stroke="var(--text-muted)" />
            <Bar dataKey="maeMw" fill={SERIES_1} barSize={40} radius={[4, 4, 0, 0]} isAnimationActive={false} />
            <Line dataKey="biasMw" stroke={SERIES_2} strokeWidth={2} dot={dot} activeDot={activeDot} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartFrame>
      <Legend items={LEGEND} />
    </>
  );
}
