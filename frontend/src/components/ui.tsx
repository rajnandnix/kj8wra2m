import type { UseQueryResult } from "@tanstack/react-query";
import type { CSSProperties, ReactNode } from "react";
import s from "./ui.module.css";

export const cx = (...c: (string | false | undefined)[]) => c.filter(Boolean).join(" ");

export function Card({
  title,
  sub,
  children,
  className,
  style,
}: {
  title?: ReactNode;
  sub?: ReactNode;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <section className={cx(s.card, className)} style={style}>
      {(title || sub) && (
        <header className={s.cardHead}>
          {title && <h2 className={s.title}>{title}</h2>}
          {sub && <p className={s.sub}>{sub}</p>}
        </header>
      )}
      {children}
    </section>
  );
}

export const Grid = ({ cols, children }: { cols: 2 | 3 | 5; children: ReactNode }) => (
  <div className={cx(s.grid, cols === 2 && s.cols2, cols === 3 && s.cols3, cols === 5 && s.cols5)}>
    {children}
  </div>
);

export function Metric({
  label,
  value,
  unit,
  note,
  secondary,
}: {
  label: string;
  value: string;
  unit?: string;
  note?: ReactNode;
  secondary?: ReactNode;
}) {
  return (
    <div className={cx(s.card, s.metric)}>
      <span className={s.metricLabel}>{label}</span>
      <span className={s.metricValue}>
        {value}
        {unit && <span className={s.metricUnit}>{unit}</span>}
      </span>
      {note && <span className={s.metricNote}>{note}</span>}
      {secondary && <span className={s.metricSecondary}>{secondary}</span>}
    </div>
  );
}

export const Skeleton = ({ height = 200, width = "100%" }: { height?: number; width?: number | string }) => (
  <div className={s.skeleton} style={{ height, width }} role="status" aria-label="Loading" />
);

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <div className={s.errorBox} role="alert">
      <strong>This panel could not load</strong>
      <span>{message}</span>
      {onRetry && (
        <button className={s.button} onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

/** Renders a skeleton while loading, an error panel with retry on failure, else the content. */
export function Async<T>({
  query,
  height = 240,
  children,
}: {
  query: UseQueryResult<T>;
  height?: number;
  children: (data: T) => ReactNode;
}) {
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  if (query.isLoading || !query.data) return <Skeleton height={height} />;
  return <>{children(query.data)}</>;
}

export const Note = ({ children }: { children: ReactNode }) => <p className={s.note}>{children}</p>;

export function Legend({ items }: { items: { label: string; color: string; kind?: "line" | "box" }[] }) {
  return (
    <div className={s.legend}>
      {items.map((i) => (
        <span key={i.label} className={s.legendItem}>
          {i.kind === "box" ? (
            <span className={s.swatchBox} style={{ background: i.color }} />
          ) : (
            <span className={s.swatchLine} style={{ borderColor: i.color }} />
          )}
          {i.label}
        </span>
      ))}
    </div>
  );
}

export function DataTable({
  head,
  rows,
}: {
  head: string[];
  rows: (string | number)[][];
}) {
  return (
    <div className={s.tableWrap}>
      <table className={s.table}>
        <thead>
          <tr>
            {head.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((c, j) => (
                <td key={j}>{c}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export const Details = ({ summary, children }: { summary: string; children: ReactNode }) => (
  <details className={s.details}>
    <summary>{summary}</summary>
    {children}
  </details>
);

export const Banner = ({ children, sub }: { children: ReactNode; sub?: ReactNode }) => (
  <div className={s.banner} role="note">
    <div className={s.bannerMain}>{children}</div>
    {sub && <div className={s.bannerSub}>{sub}</div>}
  </div>
);

export const Split = ({ children }: { children: ReactNode }) => <div className={s.split}>{children}</div>;
