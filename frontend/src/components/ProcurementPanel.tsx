import type { ForecastResponse } from "../lib/api";
import { dayLong, mw, mwh, num, pct, signedMw } from "../lib/format";
import s from "./ProcurementPanel.module.css";
import { DataTable, Details } from "./ui";

/** The product: turns the historical error distribution into a band around the forecast.
 *  Each hour uses the error quantiles of hours with a similar forecast level. */
export function ProcurementPanel({ data }: { data: ForecastResponse }) {
  const b = data.band;
  const withActual = data.forecast.filter((p) => p.actualMw != null);
  const actualMean = withActual.reduce((a, p) => a + (p.actualMw ?? 0), 0) / Math.max(1, withActual.length);
  const sampleHours = b.buckets.reduce((a, k) => a + k.n, 0);

  // Scale bar: forecast, the P10-P90 range of realised wind, and what this day actually did.
  const lo = Math.min(b.windLowMw, actualMean) - 400;
  const hi = Math.max(b.windHighMw, actualMean) + 400;
  const pc = (v: number) => ((v - lo) / (hi - lo)) * 100;
  const x = (v: number) => `${pc(v)}%`;
  const shortfall = b.coverHighMw > 0;
  const levels = [...new Set(data.forecast.map((p) => p.bandBucket).filter(Boolean))].join(", ");

  return (
    <section className={s.panel} aria-labelledby="procurement-title">
      <div>
        <div className={s.kicker}>Procurement band</div>
        <h2 id="procurement-title" style={{ fontSize: 15, fontWeight: 600, color: "var(--text-secondary)", margin: 0 }}>
          for delivery on {dayLong(data.deliveryDate)}, at the {data.cutoff.localTime} decision cutoff
        </h2>
      </div>

      <p className={s.headline}>
        On the day-ahead decision the forecast says <b>{mw(b.forecastMw)}</b> (day average). Historically, for forecasts at
        these levels, realised wind has come in between <b>{mw(b.windLowMw)}</b> and <b>{mw(b.windHighMw)}</b> (the P10
        to P90 of the forecast&apos;s error), so plan a cover requirement of{" "}
        <b>{b.coverLowMw < 0 ? `a ${mw(-b.coverLowMw)} surplus` : mw(b.coverLowMw)}</b> to{" "}
        <b>{shortfall ? `a ${mw(b.coverHighMw)} shortfall` : mw(b.coverHighMw)}</b>. At P90, the shortfall you need thermal
        cover for averages <b>{mw(b.coverP90Mw)}</b>.
      </p>

      <div className={s.figures}>
        <div className={s.figure}>
          <span className={s.figureLabel}>Day-average forecast</span>
          <span className={s.figureValue}>
            {num(b.forecastMw)}
            <small>MW</small>
          </span>
          <span className={s.figureNote}>
            Latest vintage in hand at the cutoff, mean over {b.hours} hours. Forecast levels this day: {levels}.
          </span>
        </div>
        <div className={s.figure}>
          <span className={s.figureLabel}>Realised wind, P10 to P90</span>
          <span className={s.figureValue}>
            {num(b.windLowMw)} to {num(b.windHighMw)}
            <small>MW</small>
          </span>
          <span className={s.figureNote}>
            Day average of the hourly bands: forecast minus the P90 error to forecast minus the P10 error for each hour&apos;s
            forecast level.
          </span>
        </div>
        <div className={s.figure}>
          <span className={s.figureLabel}>Thermal cover to hold at P90</span>
          <span className={s.figureValue}>
            {num(b.coverP90Mw)}
            <small>MW</small>
          </span>
          <span className={s.figureNote}>
            = <b>{mwh(b.coverP90Mwh)}</b> if each hour is covered at its own P90 (sum of hourly MW x 1 h over {b.hours} hours).
          </span>
        </div>
      </div>

      <div className={s.scaleWrap} aria-hidden="true">
        <svg width="100%" height="44" role="presentation">
          <rect x="0" y="20" width="100%" height="4" rx="2" fill="var(--grid)" />
          <rect
            x={x(b.windLowMw)}
            y="14"
            width={`${pc(b.windHighMw) - pc(b.windLowMw)}%`}
            height="16"
            rx="4"
            fill="var(--series-1)"
            fillOpacity="0.28"
          />
          <line x1={x(b.forecastMw)} x2={x(b.forecastMw)} y1="6" y2="38" stroke="var(--series-1)" strokeWidth="2" />
          <circle cx={x(actualMean)} cy="22" r="5" fill="var(--series-2)" stroke="var(--surface-1)" strokeWidth="2" />
        </svg>
        <div className={s.scaleLabels}>
          <span>{num(lo)} MW</span>
          <span>
            Forecast line (blue) · P10 to P90 range · day average actual {num(actualMean)} MW (orange dot) ·{" "}
            {data.hoursInsideBand} of {data.forecast.length} hours inside the band
          </span>
          <span>{num(hi)} MW</span>
        </div>
      </div>

      <p className={s.fine}>
        <b>How to read this.</b> Error is forecast minus actual, so a positive error means the forecast was too high and the
        day-ahead position was under-procured. <b>In-sample:</b> the band is fitted and scored on the same {sampleHours} hours
        of January 2026, including the day shown. One month cannot support out-of-sample validation, so how well it covers
        other periods is unknown and probably lower. It is an empirical band, not a probabilistic forecast, and it is
        measured against metered (FUELHH) outturn, so it carries the dataset offset described on the Accuracy view.
      </p>

      <Details summary="Band by forecast level, with in-sample coverage">
        <DataTable
          head={["Forecast level", "Hours", "P10 error", "P50 error", "P90 error", "In-sample coverage", "Single global band"]}
          rows={[
            ...b.buckets.map((k) => [
              k.bucket,
              num(k.n),
              signedMw(k.p10Mw),
              signedMw(k.p50Mw),
              signedMw(k.p90Mw),
              pct(k.coveragePct),
              pct(k.unconditionalCoveragePct),
            ]),
            ["All hours", num(sampleHours), "", "", "", pct(b.overallCoveragePct), pct(b.unconditionalCoveragePct)],
          ]}
        />
        <p className={s.fine} style={{ marginTop: 8 }}>
          Coverage is the share of hours whose actual outturn fell inside the band. The last column scores a single P10 to
          P90 pair applied to every hour: it over-covers some levels and under-covers others, which is why the band is
          conditioned on forecast level. All figures are in-sample.
        </p>
      </Details>
    </section>
  );
}
