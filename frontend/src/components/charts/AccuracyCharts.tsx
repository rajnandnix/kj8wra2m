import { useMemo } from "react";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  LabelList,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { AccuracyResponse, DayDelta, Headline } from "../../lib/api";
import { dateTimeOf, dayShort, kTick, mw, num, signedMw } from "../../lib/format";
import { Legend } from "../ui";
import { AXIS_LINE, ChartFrame, GRID, SERIES_1, TICK, TooltipBox, xLabel, yAxisProps } from "./common";

const DAY_MS = 24 * 3600 * 1000;

/** Hourly forecast error across every delivery day, worst day shaded and annotated. */
export function ErrorSeriesChart({ data }: { data: AccuracyResponse }) {
  const rows = useMemo(
    () => data.errors.map((e) => ({ t: new Date(e.time).getTime(), e: e.errorMw })),
    [data],
  );
  const first = rows[0].t;
  const last = rows[rows.length - 1].t + 3600 * 1000;
  const ticks = Array.from({ length: Math.ceil((last - first) / DAY_MS / 3) + 1 }, (_, i) => first + i * 3 * DAY_MS);
  const worst = data.worstDay;
  const wStart = worst ? new Date(`${worst.deliveryDate}T00:00:00Z`).getTime() : 0;

  return (
    <>
      <ChartFrame label="Hourly forecast error in MW for every delivery day in January 2026">
        <ResponsiveContainer width="100%" height={340}>
          <LineChart data={rows} margin={{ top: 22, right: 16, bottom: 22, left: 4 }}>
            <CartesianGrid {...GRID} />
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={[first, last]}
              ticks={ticks}
              tickFormatter={(t: number) => dayShort(new Date(t).toISOString())}
              tick={TICK}
              axisLine={AXIS_LINE}
              tickLine={false}
              label={xLabel("Delivery time (UTC)")}
            />
            <YAxis {...yAxisProps("Forecast error (MW)")} />
            <Tooltip
              cursor={{ stroke: "var(--text-muted)", strokeDasharray: "3 3" }}
              content={({ payload }) => {
                if (!payload?.length) return null;
                const r = payload[0].payload as { t: number; e: number | null };
                return (
                  <TooltipBox
                    title={`${dateTimeOf(new Date(r.t).toISOString())} UTC`}
                    rows={[{ label: "Error (forecast − actual)", value: signedMw(r.e), color: SERIES_1 }]}
                  />
                );
              }}
            />
            <ReferenceLine y={0} stroke="var(--text-muted)" />
            {worst && (
              <ReferenceArea
                x1={wStart}
                x2={wStart + DAY_MS}
                fill="var(--series-2)"
                fillOpacity={0.14}
                ifOverflow="visible"
                label={{
                  value: `Worst day ${dayShort(worst.deliveryDate)}: MAE ${mw(worst.maeMw)}`,
                  position: "top",
                  fill: "var(--text-secondary)",
                  fontSize: 12,
                }}
              />
            )}
            <Line
              dataKey="e"
              stroke={SERIES_1}
              strokeWidth={1.5}
              strokeLinejoin="round"
              dot={false}
              activeDot={{ r: 5, stroke: "var(--surface-1)", strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </ChartFrame>
      <Legend
        items={[
          { label: "Hourly error, forecast − actual (above zero = forecast too high = under-procured)", color: SERIES_1 },
          { label: "Worst delivery day by MAE", color: "rgba(235,104,52,0.35)", kind: "box" },
        ]}
      />
    </>
  );
}

/** Distribution of error as a stepped outline so the percentile markers sit at exact positions. */
export function ErrorHistogram({ data }: { data: AccuracyResponse }) {
  const h: Headline = data.headline;
  const rows = useMemo(() => {
    const pts = data.histogram.map((b) => ({ x: b.fromMw, count: b.count }));
    const lastBin = data.histogram[data.histogram.length - 1];
    pts.push({ x: lastBin.toMw, count: lastBin.count });
    return pts;
  }, [data]);
  const marks = [
    { v: h.p10Mw, name: "P10" },
    { v: h.p50Mw, name: "P50" },
    { v: h.p90Mw, name: "P90" },
  ];
  const lo = rows[0].x;
  const hi = rows[rows.length - 1].x;
  const xTicks: number[] = [];
  for (let v = Math.ceil(lo / 1000) * 1000; v <= hi; v += 1000) xTicks.push(v);
  return (
    <>
      <ChartFrame label="Distribution of hourly forecast error with the P10, P50 and P90 marked">
        <ResponsiveContainer width="100%" height={340}>
          <ComposedChart data={rows} margin={{ top: 22, right: 16, bottom: 22, left: 4 }}>
            <CartesianGrid {...GRID} />
            <XAxis
              dataKey="x"
              type="number"
              domain={[lo, hi]}
              ticks={xTicks}
              tickFormatter={kTick}
              tick={TICK}
              axisLine={AXIS_LINE}
              tickLine={false}
              label={xLabel("Forecast error (MW), forecast − actual")}
            />
            <YAxis
              tick={TICK}
              tickLine={false}
              axisLine={false}
              width={44}
              label={{
                value: "Hourly intervals",
                angle: -90,
                position: "insideLeft",
                offset: 8,
                style: { fill: "var(--text-secondary)", fontSize: 12, textAnchor: "middle" },
              }}
            />
            <Tooltip
              cursor={{ stroke: "var(--text-muted)", strokeDasharray: "3 3" }}
              content={({ payload }) => {
                if (!payload?.length) return null;
                const r = payload[0].payload as { x: number; count: number };
                return (
                  <TooltipBox
                    title={`${signedMw(r.x)} to ${signedMw(r.x + 500)}`}
                    rows={[{ label: "Hourly intervals", value: String(r.count), color: SERIES_1 }]}
                  />
                );
              }}
            />
            <Area
              dataKey="count"
              type="stepAfter"
              stroke={SERIES_1}
              strokeWidth={2}
              fill={SERIES_1}
              fillOpacity={0.12}
              isAnimationActive={false}
              activeDot={{ r: 5, stroke: "var(--surface-1)", strokeWidth: 2 }}
            />
            <ReferenceLine x={0} stroke="var(--text-muted)" />
            {marks.map(
              (m) =>
                m.v != null && (
                  <ReferenceLine
                    key={m.name}
                    x={m.v}
                    stroke="var(--text-secondary)"
                    strokeDasharray="4 3"
                    label={{
                      value: `${m.name} ${num(m.v)}`,
                      position: "top",
                      fill: "var(--text-secondary)",
                      fontSize: 12,
                    }}
                  />
                ),
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </ChartFrame>
      <Legend
        items={[
          { label: "Number of hourly intervals per 500 MW error band", color: SERIES_1 },
          { label: "Dashed lines: P10, P50 (median) and P90 of error; solid line: zero error", color: "var(--text-secondary)" },
        ]}
      />
    </>
  );
}

/** Single-series bar chart of MAE per cutoff with the value at each bar tip. */
export function CutoffMaeChart({ rows }: { rows: { name: string; mae: number }[] }) {
  return (
    <ChartFrame label="Mean absolute error in MW at each decision cutoff">
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={rows} margin={{ top: 22, right: 16, bottom: 22, left: 4 }}>
          <CartesianGrid {...GRID} />
          <XAxis dataKey="name" tick={TICK} axisLine={AXIS_LINE} tickLine={false} />
          <YAxis {...yAxisProps("Mean absolute error (MW)")} domain={[0, "auto"]} />
          <Tooltip
            cursor={{ fill: "var(--surface-2)" }}
            content={({ payload }) => {
              if (!payload?.length) return null;
              const r = payload[0].payload as { name: string; mae: number };
              return <TooltipBox title={r.name} rows={[{ label: "MAE", value: mw(r.mae), color: SERIES_1 }]} />;
            }}
          />
          <Bar dataKey="mae" fill={SERIES_1} barSize={48} radius={[4, 4, 0, 0]} isAnimationActive={false}>
            <LabelList
              dataKey="mae"
              position="top"
              formatter={(v: number) => num(v)}
              style={{ fill: "var(--text-primary)", fontSize: 12.5, fontWeight: 600 }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}


/** Day-by-day change in MAE at an alternative cutoff. Days that get worse are drawn in a
 *  different colour so they cannot be averaged away. */
export function DayDeltaChart({ days, label }: { days: DayDelta[]; label: string }) {
  return (
    <>
      <ChartFrame label={`Change in daily MAE in MW for each delivery day at the ${label} cutoff against 09:20`}>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={days} margin={{ top: 12, right: 16, bottom: 22, left: 4 }}>
            <CartesianGrid {...GRID} />
            <XAxis
              dataKey="deliveryDate"
              tick={TICK}
              axisLine={AXIS_LINE}
              tickLine={false}
              interval={2}
              tickFormatter={(d: string) => dayShort(`${d}T00:00:00Z`)}
              label={xLabel("Delivery day")}
            />
            <YAxis {...yAxisProps("Change in daily MAE (MW)")} />
            <ReferenceLine y={0} stroke="var(--text-muted)" />
            <Tooltip
              cursor={{ fill: "var(--surface-2)" }}
              content={({ payload }) => {
                if (!payload?.length) return null;
                const r = payload[0].payload as DayDelta;
                return (
                  <TooltipBox
                    title={dayShort(`${r.deliveryDate}T00:00:00Z`)}
                    rows={[
                      { label: "MAE at 09:20", value: mw(r.maeBaselineMw) },
                      { label: `MAE at ${label}`, value: mw(r.maeAlternativeMw) },
                      { label: r.deltaMw > 0 ? "Worse by" : "Better by", value: mw(Math.abs(r.deltaMw)), color: r.deltaMw > 0 ? "var(--worse)" : SERIES_1 },
                    ]}
                  />
                );
              }}
            />
            <Bar dataKey="deltaMw" barSize={12} radius={[3, 3, 3, 3]} isAnimationActive={false}>
              {days.map((d) => (
                <Cell key={d.deliveryDate} fill={d.deltaMw > 0 ? "var(--worse)" : SERIES_1} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </ChartFrame>
      <Legend
        items={[
          { label: "Day better at the later gate (MAE falls)", color: SERIES_1, kind: "box" },
          { label: "Day worse at the later gate (MAE rises)", color: "var(--worse)", kind: "box" },
        ]}
      />
    </>
  );
}
