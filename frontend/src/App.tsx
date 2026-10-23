import { useState } from "react";
import { Footer } from "./components/Footer";
import { Async } from "./components/ui";
import { useHealth } from "./hooks/useApi";
import { AccuracyPage } from "./pages/AccuracyPage";
import { BreakdownPage } from "./pages/BreakdownPage";
import { DecisionPage } from "./pages/DecisionPage";
import s from "./pages/Pages.module.css";

const TABS = [
  { id: "decision", label: "Decision view" },
  { id: "accuracy", label: "Accuracy view" },
  { id: "breakdown", label: "Breakdown view" },
] as const;

type Tab = (typeof TABS)[number]["id"];

export default function App() {
  const health = useHealth();
  const [tab, setTabState] = useState<Tab>(() => {
    const h = window.location.hash.slice(1);
    return TABS.some((t) => t.id === h) ? (h as Tab) : "decision";
  });
  const setTab = (t: Tab) => {
    window.location.hash = t;
    setTabState(t);
  };
  const [cutoff, setCutoff] = useState<string>();
  const cutoffKey = cutoff ?? health.data?.primaryCutoff ?? "epex60";

  return (
    <div className={s.app}>
      <header className={s.header}>
        <div className={s.brand}>
          <h1>GB day-ahead wind forecast risk</h1>
          <p>The forecast you had at decision time, and how wrong it has been. January 2026 decisions.</p>
        </div>
        <div className={s.cutoffBox}>
          <label htmlFor="cutoff">Decision cutoff (gate closure on D-1)</label>
          <select id="cutoff" className={s.select} value={cutoffKey} onChange={(e) => setCutoff(e.target.value)} disabled={!health.data}>
            {(health.data?.cutoffs ?? []).map((c) => (
              <option key={c.key} value={c.key}>
                {c.localTime} {c.label}
                {c.key === health.data?.primaryCutoff ? " (primary)" : ""}
              </option>
            ))}
            {!health.data && <option value={cutoffKey}>Loading…</option>}
          </select>
        </div>
      </header>

      <nav className={s.tabs} aria-label="Views">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={`${s.tab} ${tab === t.id ? s.tabActive : ""}`}
            aria-current={tab === t.id ? "page" : undefined}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main>
        {health.isError ? (
          <Async query={health}>{() => null}</Async>
        ) : (
          <>
            {tab === "decision" && <DecisionPage cutoffKey={cutoffKey} />}
            {tab === "accuracy" && <AccuracyPage cutoffKey={cutoffKey} />}
            {tab === "breakdown" && <BreakdownPage cutoffKey={cutoffKey} />}
          </>
        )}
      </main>

      <Footer cutoffKey={cutoffKey} />
    </div>
  );
}
