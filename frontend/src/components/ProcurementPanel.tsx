import type { ForecastResponse } from "../lib/api";
import { dayLong, mw, mwh, num, signedMw } from "../lib/format";
import s from "./ProcurementPanel.module.css";

/** The product: turns the historical error distribution into a band around the forecast. */
export function ProcurementPanel({ data }: { data: ForecastResponse }) {
  const b = data.band;
  const actualMean =
    data.forecast.reduce((a, p) => a + (p.actualMw ?? 0), 0) / Math.max(1, data.forecast.filter((p) => p.actualMw != null).length);

  // Scale bar: forecast, the P10-P90 range of realised wind, and what this day actually did.
  const lo = Math.min(b.windLowMw, actualMean) - 400;
  const hi = Math.max(b.windHighMw, actualMean) + 400;
  const pc = (v: number) => ((v - lo) / (hi - lo)) * 100;
  const x = (v: number) => `${pc(v)}%`;
  const shortfall = b.coverHighMw > 0;

  return (
    <section className={s.panel} aria-labelledby="procurement-title">
      <div>
        <div className={s.kicker}>Procurement band</div>
        <h2 id="procurement-title" style={{ fontSize: 15, fontWeight: 600, color: "var(--text-secondary)", margin: 0 }}>
          for delivery on {dayLong(data.deliveryDate)}, at the {data.cutoff.localTime} decision cutoff
        </h2>
      </div>

      <p className={s.headline}>
        On the day-ahead decision the forecast says <b>{mw(b.forecastMw)}</b>. Historically realised wind has come in
        between <b>{mw(b.windLowMw)}</b> and <b>{mw(b.windHighMw)}</b> (the P10 to P90 of this forecast&apos;s error), so
        plan a cover requirement of{" "}
        <b>{b.coverLowMw < 0 ? `a ${mw(-b.coverLowMw)} surplus` : mw(b.coverLowMw)}</b> to{" "}
        <b>{shortfall ? `a ${mw(b.coverHighMw)} shortfall` : mw(b.coverHighMw)}</b>. At P90, the shortfall you need
        thermal cover for is <b>{mw(b.coverP90Mw)}</b>.
      </p>

      <div className={s.figures}>
        <div className={s.figure}>
          <span className={s.figureLabel}>Day-average forecast</span>
          <span className={s.figureValue}>
            {num(b.forecastMw)}
            <small>MW</small>
          </span>
          <span className={s.figureNote}>
            Latest vintage in hand at the cutoff, mean over {b.hours} hours.
          </span>
        </div>
        <div className={s.figure}>
          <span className={s.figureLabel}>Realised wind, P10 to P90</span>
          <span className={s.figureValue}>
            {num(b.windLowMw)} to {num(b.windHighMw)}
            <small>MW</small>
          </span>
          <span className={s.figureNote}>
            Forecast minus P90 error ({signedMw(b.p90ErrorMw)}) to forecast minus P10 error ({signedMw(b.p10ErrorMw)}).
          </span>
        </div>
        <div className={s.figure}>
          <span className={s.figureLabel}>Thermal cover to hold at P90</span>
          <span className={s.figureValue}>
            {num(b.coverP90Mw)}
            <small>MW</small>
          </span>
          <span className={s.figureNote}>
            = <b>{mwh(b.coverP90Mwh)}</b> if held for all {b.hours} hours ({num(b.coverP90Mw)} MW x {b.hours} h).
          </span>
        </div>
      </div>

      <div className={s.scaleWrap} aria-hidden="true">
        <svg width="100%" height="44" role="presentation">
          <rect x="0" y="20" width="100%" height="4" rx="2" fill="var(--grid)" />
          <rect x={x(b.windLowMw)} y="14" width={`${pc(b.windHighMw) - pc(b.windLowMw)}%`} height="16" rx="4" fill="var(--series-1)" fillOpacity="0.28" />
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
        day-ahead position was under-procured. {data.band.basis} The band is not corrected for the standing positive bias (see the Accuracy view).
      </p>
    </section>
  );
}
