import { useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ForecastResponse } from "../../lib/api";
import { mw, signedMw, timeOf } from "../../lib/format";
import { Legend } from "../ui";
import { AXIS_LINE, ChartFrame, GRID, SERIES_1, SERIES_2, TICK, TooltipBox, xLabel, yAxisProps } from "./common";

interface Row {
  t: number;
  forecast?: number;
  actual?: number;
  band?: [number, number];
  low?: number;
  high?: number;
}

function buildRows(d: ForecastResponse): Row[] {
  const rows = new Map<number, Row>();
  const at = (iso: string) => {
    const t = new Date(iso).getTime();
    if (!rows.has(t)) rows.set(t, { t });
    return rows.get(t) as Row;
  };
  for (const p of d.forecast) {
    const r = at(p.time);
    if (p.forecastMw != null) r.forecast = p.forecastMw;
    if (p.windLowMw != null && p.windHighMw != null) {
      r.band = [p.windLowMw, p.windHighMw];
      r.low = p.windLowMw;
      r.high = p.windHighMw;
    }
  }
  for (const a of d.actualsHalfHourly) at(a.time).actual = a.mw;
  return [...rows.values()].sort((a, b) => a.t - b.t);
}

export function DecisionChart({ data }: { data: ForecastResponse }) {
  const rows = useMemo(() => buildRows(data), [data]);
  const start = new Date(data.forecast[0].time).getTime();
  const end = start + 24 * 3600 * 1000;
  const ticks = Array.from({ length: 9 }, (_, i) => start + i * 3 * 3600 * 1000);

  return (
    <>
      <ChartFrame
        label={`Decision-time wind forecast versus actual outturn for ${data.deliveryDate}, with the empirical P10 to P90 band`}
      >
        <ResponsiveContainer width="100%" height={380}>
          <ComposedChart data={rows} margin={{ top: 8, right: 16, bottom: 22, left: 4 }}>
            <CartesianGrid {...GRID} />
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={[start, end]}
              ticks={ticks}
              tickFormatter={(t: number) => timeOf(new Date(t).toISOString())}
              tick={TICK}
              axisLine={AXIS_LINE}
              tickLine={false}
              label={xLabel("Time of delivery day (UTC)")}
            />
            <YAxis {...yAxisProps("Wind generation (MW)")} domain={["auto", "auto"]} />
            <Tooltip
              cursor={{ stroke: "var(--text-muted)", strokeDasharray: "3 3" }}
              content={({ payload, label }) => {
                if (!payload?.length) return null;
                const r = payload[0].payload as Row;
                const lines = [];
                if (r.forecast != null)
                  lines.push({ label: "Forecast", value: mw(r.forecast), color: SERIES_1 });
                if (r.low != null && r.high != null)
                  lines.push({ label: "P10 to P90 band", value: `${mw(r.low)} to ${mw(r.high)}` });
                if (r.actual != null) lines.push({ label: "Actual", value: mw(r.actual), color: SERIES_2 });
                if (r.forecast != null && r.actual != null)
                  lines.push({ label: "Error (forecast − actual)", value: signedMw(r.forecast - r.actual) });
                return <TooltipBox title={`${timeOf(new Date(label as number).toISOString())} UTC`} rows={lines} />;
              }}
            />
            <Area
              dataKey="band"
              stroke="none"
              fill="var(--series-1)"
              fillOpacity={0.12}
              connectNulls
              isAnimationActive={false}
              activeDot={false}
            />
            <Line
              dataKey="forecast"
              stroke={SERIES_1}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              dot={{ r: 4, fill: SERIES_1, stroke: "var(--surface-1)", strokeWidth: 2 }}
              activeDot={{ r: 5, stroke: "var(--surface-1)", strokeWidth: 2 }}
              connectNulls
              isAnimationActive={false}
            />
            <Line
              dataKey="actual"
              stroke={SERIES_2}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              dot={false}
              activeDot={{ r: 5, stroke: "var(--surface-1)", strokeWidth: 2 }}
              connectNulls
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </ChartFrame>
      <Legend
        items={[
          { label: "Forecast available at the cutoff (hourly)", color: SERIES_1 },
          { label: "Actual outturn (half-hourly)", color: SERIES_2 },
          { label: "Empirical P10 to P90 band around the forecast", color: "rgba(42,120,214,0.25)", kind: "box" },
        ]}
      />
    </>
  );
}
