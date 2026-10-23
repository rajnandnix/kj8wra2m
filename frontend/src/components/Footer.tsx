import { useHealth } from "../hooks/useApi";
import { dayLong } from "../lib/format";
import s from "./Footer.module.css";

export function Footer({ cutoffKey }: { cutoffKey: string }) {
  const { data } = useHealth();
  const cutoff = data?.cutoffs.find((c) => c.key === cutoffKey);
  return (
    <footer className={s.footer}>
      <div className={s.grid}>
        <div>
          <h3>Data source</h3>
          <p>
            Elexon BMRS Insights API. Forecast: <b>WINDFOR</b> (hourly, 8 publications a day). Actual outturn:{" "}
            <b>FUELHH</b> wind (half-hourly, averaged to the hour). No other data is used.
          </p>
        </div>
        <div>
          <h3>Window</h3>
          <p>
            {data ? (
              <>
                Decisions {dayLong(data.dataWindow.decisionFrom)} to {dayLong(data.dataWindow.decisionTo)}; delivery{" "}
                {dayLong(data.dataWindow.deliveryFrom)} to {dayLong(data.dataWindow.deliveryTo)}. Fixed snapshot built{" "}
                {data.buildTimestamp.slice(0, 10)}; no live calls at request time.
              </>
            ) : (
              "Loading window…"
            )}
          </p>
        </div>
        <div>
          <h3>Cutoff assumption</h3>
          <p>{cutoff ? cutoff.rule : "Loading cutoff rule…"} Times are UTC; in January London time equals UTC.</p>
        </div>
        <div>
          <h3>Scope caveat</h3>
          <p>
            National GB, wind only. FUELHH covers transmission-metered, BM-registered wind; embedded wind is excluded.
            The two datasets are not equivalent in scope: WINDFOR runs about 13 to 16% above FUELHH, which this tool reports
            as bias, not as forecast skill.
          </p>
        </div>
      </div>
    </footer>
  );
}
