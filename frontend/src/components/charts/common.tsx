import type { ReactNode } from "react";
import { kTick } from "../../lib/format";

export const TICK = { fill: "var(--text-muted)", fontSize: 12 } as const;
export const GRID = { stroke: "var(--grid)", vertical: false } as const;
export const AXIS_LINE = { stroke: "var(--border)" } as const;
export const SERIES_1 = "var(--series-1)";
export const SERIES_2 = "var(--series-2)";
export const SURFACE = "var(--surface-1)";

export const yAxisProps = (label: string) => ({
  tick: TICK,
  tickLine: false,
  axisLine: false,
  tickFormatter: kTick,
  width: 56,
  label: {
    value: label,
    angle: -90,
    position: "insideLeft" as const,
    offset: 4,
    style: { fill: "var(--text-secondary)", fontSize: 12, textAnchor: "middle" as const },
  },
});

export const xLabel = (value: string) => ({
  value,
  position: "insideBottom" as const,
  offset: -2,
  style: { fill: "var(--text-secondary)", fontSize: 12 },
});

export function ChartFrame({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div role="img" aria-label={label}>
      {children}
    </div>
  );
}

export function TooltipBox({ title, rows }: { title: string; rows: { label: string; value: string; color?: string }[] }) {
  return (
    <div
      style={{
        background: "var(--surface-1)",
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: "8px 12px",
        fontSize: 12.5,
        boxShadow: "0 4px 14px rgba(0,0,0,0.12)",
        color: "var(--text-primary)",
      }}
    >
      <div style={{ fontWeight: 650, marginBottom: 4 }}>{title}</div>
      {rows.map((r) => (
        <div key={r.label} style={{ display: "flex", gap: 14, justifyContent: "space-between" }}>
          <span style={{ color: "var(--text-secondary)", display: "inline-flex", alignItems: "center", gap: 6 }}>
            {r.color && <span style={{ width: 8, height: 8, borderRadius: 4, background: r.color, display: "inline-block" }} />}
            {r.label}
          </span>
          <span style={{ fontVariantNumeric: "tabular-nums" }}>{r.value}</span>
        </div>
      ))}
    </div>
  );
}
