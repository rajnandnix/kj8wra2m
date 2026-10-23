// All times are shown in UTC. In January London time equals UTC, which the UI states.

const utc = (opts: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", ...opts });

const fmtTime = utc({ hour: "2-digit", minute: "2-digit", hour12: false });
const fmtDay = utc({ day: "numeric", month: "short", year: "numeric" });
const fmtDayShort = utc({ day: "numeric", month: "short" });
const fmtDayLong = utc({ weekday: "short", day: "numeric", month: "short", year: "numeric" });

export const timeOf = (iso: string) => fmtTime.format(new Date(iso));
export const dayOf = (iso: string) => fmtDay.format(new Date(iso));
export const dayShort = (iso: string) => fmtDayShort.format(new Date(iso));
export const dayLong = (isoDate: string) => fmtDayLong.format(new Date(`${isoDate}T00:00:00Z`));
export const dateTimeOf = (iso: string) => `${fmtDayShort.format(new Date(iso))} ${timeOf(iso)}`;

const grouped = (v: number, digits: number) =>
  v.toLocaleString("en-GB", { maximumFractionDigits: digits, minimumFractionDigits: digits });

export function num(v: number | null | undefined, digits = 0): string {
  return v == null ? "n/a" : grouped(v, digits);
}

export function mw(v: number | null | undefined, digits = 0): string {
  return v == null ? "n/a" : `${grouped(v, digits)} MW`;
}

export function signedMw(v: number | null | undefined, digits = 0): string {
  if (v == null) return "n/a";
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  return `${sign}${grouped(Math.abs(v), digits)} MW`;
}

export function pct(v: number | null | undefined, digits = 1): string {
  return v == null ? "n/a" : `${v.toFixed(digits)}%`;
}

export function signedPct(v: number, digits = 1): string {
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  return `${sign}${Math.abs(v).toFixed(digits)}%`;
}

export const mwh = (v: number) => `${num(v)} MWh`;

/** Axis tick for MW values: 12000 becomes 12k. */
export const kTick = (v: number) =>
  Math.abs(v) >= 1000 ? `${(v / 1000).toLocaleString("en-GB")}k` : `${v}`;
