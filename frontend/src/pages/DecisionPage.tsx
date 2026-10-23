import { useEffect, useMemo, useState } from "react";
import { DecisionChart } from "../components/charts/DecisionChart";
import { ProcurementPanel } from "../components/ProcurementPanel";
import { Async, Banner, Card, DataTable, Details, Skeleton } from "../components/ui";
import { useForecast, useHealth } from "../hooks/useApi";
import { dateTimeOf, dayLong, mw, signedMw, timeOf } from "../lib/format";
import s from "./Pages.module.css";

function addDays(iso: string, n: number) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export function DecisionPage({ cutoffKey }: { cutoffKey: string }) {
  const health = useHealth();
  const [day, setDay] = useState<string>();

  useEffect(() => {
    if (!day && health.data) setDay(health.data.defaultDeliveryDate);
  }, [day, health.data]);

  const from = health.data?.dataWindow.deliveryFrom;
  const to = health.data?.dataWindow.deliveryTo;
  const days = useMemo(() => {
    if (!from || !to) return [];
    const out: string[] = [];
    for (let d = from; d <= to; d = addDays(d, 1)) out.push(d);
    return out;
  }, [from, to]);

  const forecast = useForecast(day, cutoffKey);

  return (
    <div className={s.stack}>
      <div className={s.controls}>
        <label htmlFor="delivery-day">Delivery day</label>
        <button className={s.stepBtn} aria-label="Previous day" disabled={!day || day <= (from ?? "")} onClick={() => day && setDay(addDays(day, -1))}>
          ‹
        </button>
        <select id="delivery-day" className={s.select} style={{ minWidth: 200 }} value={day ?? ""} onChange={(e) => setDay(e.target.value)} disabled={!days.length}>
          {days.map((d) => (
            <option key={d} value={d}>
              {dayLong(d)}
              {d === health.data?.largestMissDate ? "  (largest miss)" : ""}
            </option>
          ))}
        </select>
        <button className={s.stepBtn} aria-label="Next day" disabled={!day || day >= (to ?? "")} onClick={() => day && setDay(addDays(day, 1))}>
          ›
        </button>
      </div>

      {health.isError && <Async query={health}>{() => null}</Async>}

      {health.data && day !== health.data.sensitivityExampleDate && (
        <p style={{ margin: 0, fontSize: 13.5, color: "var(--text-secondary)" }}>
          Want the case for buying later?{" "}
          <button className={s.linkBtn} onClick={() => setDay(health.data?.sensitivityExampleDate)}>
            Jump to {dayLong(health.data.sensitivityExampleDate)}
          </button>
          , the day the 11:30 forecast revised the 07:30 and 09:30 ones sharply, so the 15:30 gate would have roughly halved the error.
        </p>
      )}

      <Async query={forecast} height={90}>
        {(d) => {
          const times = d.vintagePublishTimes;
          return (
            <Banner
              sub={
                <>
                  Decision cutoff: {d.cutoffLocal} ({timeOf(d.cutoffUtc)} UTC). {d.cutoff.rule}
                </>
              }
            >
              Forecast as published at{" "}
              <b>
                {times.length === 1
                  ? `${dateTimeOf(times[0])} UTC`
                  : times.map((t) => `${dateTimeOf(t)}`).join(" and ") + " UTC"}
              </b>
              , the latest available before the <b>{d.cutoff.localTime}</b> decision cutoff ({d.cutoff.label}). Nothing
              published after the cutoff is used.
            </Banner>
          );
        }}
      </Async>

      <Card
        title="Forecast available at decision time versus what happened"
        sub="Hourly forecast from the latest publication in hand at the cutoff, against half-hourly metered outturn. Error = forecast − actual."
      >
        <Async query={forecast} height={420}>
          {(d) => (
            <>
              <DecisionChart data={d} />
              <Details summary="View hourly values as a table">
                <DataTable
                  head={["Hour (UTC)", "Forecast", "P10 to P90 band", "Actual (hour mean)", "Error", "Lead time"]}
                  rows={d.forecast.map((p) => [
                    timeOf(p.time),
                    mw(p.forecastMw),
                    p.windLowMw != null && p.windHighMw != null ? `${mw(p.windLowMw)} to ${mw(p.windHighMw)}` : "n/a",
                    mw(p.actualMw),
                    signedMw(p.errorMw),
                    p.leadTimeH != null ? `${p.leadTimeH.toFixed(1)} h` : "n/a",
                  ])}
                />
              </Details>
            </>
          )}
        </Async>
      </Card>

      <Async query={forecast} height={360}>{(d) => <ProcurementPanel data={d} />}</Async>

      <Card
        title="The same day at each decision cutoff"
        sub="A later gate closure admits a later WINDFOR publication. Full-window comparison is on the Accuracy view."
      >
        {forecast.data ? (
          <DataTable
            head={["Cutoff (D-1, London)", "Cutoff (UTC)", "WINDFOR vintage used (UTC)", "MAE this day", "Bias this day"]}
            rows={forecast.data.otherCutoffs.map((o) => [
              `${o.cutoff.localTime} ${o.cutoff.label}${o.cutoff.key === forecast.data?.cutoff.key ? " (selected)" : ""}`,
              dateTimeOf(o.cutoffUtc),
              o.vintagePublishTimes.map(dateTimeOf).join(", ") || "none",
              mw(o.maeMw),
              signedMw(o.biasMw),
            ])}
          />
        ) : (
          <Skeleton height={120} />
        )}
      </Card>
    </div>
  );
}
