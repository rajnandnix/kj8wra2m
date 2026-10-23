"""Phase 1 spike. Throwaway: replaces assumptions with measured facts.

Usage: python scripts/explore.py [sample|params|ladder|analyze|burst|all]

Every 200 response is cached to data/raw/explore/ so re-runs make no network calls.
"""
import json
import re
import sys
import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pandas as pd

BASE = "https://data.elexon.co.uk/bmrs/api/v1/datasets"
RAW = Path(__file__).resolve().parents[1] / "data" / "raw" / "explore"
RAW.mkdir(parents=True, exist_ok=True)
UTC = timezone.utc
LONDON = ZoneInfo("Europe/London")
CLIENT = httpx.Client(timeout=180, headers={"Accept": "application/json"})
LOG: list[dict] = []
PAUSE_S = 0.6


def iso(d: datetime) -> str:
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def get(dataset: str, params: dict, label: str) -> dict:
    """GET /datasets/{dataset}/stream. Returns {url,status,elapsed_s,headers,body}."""
    path = RAW / f"{dataset}_{label}.json"
    if path.exists():
        return json.loads(path.read_text())
    t0 = time.time()
    r = CLIENT.get(f"{BASE}/{dataset}/stream", params=params)
    elapsed = round(time.time() - t0, 2)
    try:
        body = r.json()
    except ValueError:
        body = r.text
    keep = {k: v for k, v in r.headers.items()
            if any(s in k.lower() for s in ("limit", "retry", "quota", "cache-control", "content-type"))}
    rec = {"url": str(r.url), "status": r.status_code, "elapsed_s": elapsed,
           "bytes": len(r.content), "headers": keep, "body": body}
    LOG.append({k: rec[k] for k in ("url", "status", "elapsed_s")})
    if r.status_code == 200:
        path.write_text(json.dumps(rec))
    time.sleep(PAUSE_S)
    return rec


def df_of(rec: dict) -> pd.DataFrame:
    body = rec["body"]
    if not isinstance(body, list):
        return pd.DataFrame()
    df = pd.DataFrame(body)
    for c in ("startTime", "publishTime"):
        if c in df:
            df[c] = pd.to_datetime(df[c], utc=True)
    return df


def span(df: pd.DataFrame, col: str) -> str:
    return f"{df[col].min()} -> {df[col].max()}" if len(df) else "empty"


def load(dataset: str, start: datetime, end: datetime, chunk_days: int, tag: str, extra=None) -> pd.DataFrame:
    """Chunked publishDateTime fetch. Boundary duplicates removed and reported."""
    frames, s = [], start
    while s < end:
        e = min(s + timedelta(days=chunk_days), end)
        label = f"{tag}_{s:%Y%m%d}_{(e - s).days}d"
        rec = get(dataset, {"publishDateTimeFrom": iso(s), "publishDateTimeTo": iso(e), **(extra or {})}, label)
        if rec["status"] != 200:
            raise SystemExit(f"chunk {label} failed: {rec['status']} {str(rec['body'])[:200]}")
        frames.append(df_of(rec))
        s = e
    df = pd.concat(frames, ignore_index=True)
    n = len(df)
    df = df.drop_duplicates()
    print(f"  loaded {dataset}/{tag}: {n} rows, {n - len(df)} exact duplicates at chunk boundaries removed")
    return df


def head(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


# --------------------------------------------------------------------------- sample
S3_FROM, S3_TO = datetime(2026, 1, 14, tzinfo=UTC), datetime(2026, 1, 17, tzinfo=UTC)


def part_sample() -> None:
    head("Q1-Q3: working URLs, parameters, envelope (3 day sample, 14-17 Jan 2026, by publishDateTime)")
    p = {"publishDateTimeFrom": iso(S3_FROM), "publishDateTimeTo": iso(S3_TO)}
    fa = get("FUELHH", p, "sample3d_allfuels")
    fw = get("FUELHH", {**p, "fuelType": "WIND"}, "sample3d_WIND")
    wf = get("WINDFOR", p, "sample3d")
    for name, rec in (("FUELHH all fuels", fa), ("FUELHH fuelType=WIND", fw), ("WINDFOR", wf)):
        print(f"\n{name}\n  URL: {rec['url']}\n  status={rec['status']} bytes={rec['bytes']} "
              f"elapsed={rec['elapsed_s']}s envelope={type(rec['body']).__name__} rows={len(rec['body'])}")
        print("  first row:", json.dumps(rec["body"][0]))
    a, w = df_of(fa), df_of(fw)
    print("\n  FUELHH fuelType values (all fuels):", sorted(a["fuelType"].unique()))
    print("  keys:", sorted(fa["body"][0]), "| WINDFOR keys:", sorted(wf["body"][0]))
    client_side = a[a.fuelType == "WIND"].reset_index(drop=True)
    same = client_side.sort_values(["startTime", "publishTime"]).reset_index(drop=True).equals(
        w.sort_values(["startTime", "publishTime"]).reset_index(drop=True))
    print(f"  server-side fuelType=WIND == client-side filter of all fuels: {same} "
          f"({len(w)} vs {len(client_side)} rows)")
    print("  FUELHH WIND publishTime span:", span(w, "publishTime"), "| startTime span:", span(w, "startTime"))
    wfd = df_of(wf)
    print("  WINDFOR publishTime span:", span(wfd, "publishTime"), "| startTime span:", span(wfd, "startTime"))


# --------------------------------------------------------------------------- params
def part_params() -> None:
    head("Query parameter traps: do unknown or alternative names filter, or get ignored silently?")
    win = "14 Jan 00:00 -> 17 Jan 00:00"
    cases = [
        ("FUELHH", "from/to", {"from": iso(S3_FROM), "to": iso(S3_TO), "fuelType": "WIND"}),
        ("WINDFOR", "from/to", {"from": iso(S3_FROM), "to": iso(S3_TO)}),
        ("FUELHH", "settlementDateFrom/To", {"settlementDateFrom": "2026-01-14", "settlementDateTo": "2026-01-16",
                                              "fuelType": "WIND"}),
        ("WINDFOR", "settlementDateFrom/To", {"settlementDateFrom": "2026-01-14", "settlementDateTo": "2026-01-16"}),
        ("WINDFOR", "no params at all", {}),
    ]
    print(f"requested window: {win}")
    for ds, name, params in cases:
        rec = get(ds, params, "param_" + re.sub(r"\W+", "_", name))
        d = df_of(rec)
        pub = span(d, "publishTime") if len(d) else "-"
        print(f"\n{ds} {name}: status={rec['status']} rows={len(d)}\n  publishTime span: {pub}"
              f"\n  startTime span:   {span(d, 'startTime') if len(d) else '-'}"
              f"\n  body if not rows: {'' if len(d) else str(rec['body'])[:300]}")


# --------------------------------------------------------------------------- ladder
LADDER_START = datetime(2025, 12, 28, tzinfo=UTC)
LADDER = [1, 7, 14, 31, 36, 60, 90]


def part_ladder() -> None:
    head("Q11: maximum date span per request (publishDateTime), from 28 Dec 2025")
    for ds, extra in (("FUELHH", {"fuelType": "WIND"}), ("WINDFOR", {})):
        print(f"\n{ds}")
        prev_rows = 0
        for n in LADDER:
            e = LADDER_START + timedelta(days=n)
            rec = get(ds, {"publishDateTimeFrom": iso(LADDER_START), "publishDateTimeTo": iso(e), **extra},
                      f"ladder_{n}d")
            if rec["status"] != 200:
                print(f"  {n:>3}d: FAILED status={rec['status']} body={str(rec['body'])[:300]}")
                break
            d = df_of(rec)
            ok = "ok" if len(d) >= prev_rows else "ROWS DECREASED"
            print(f"  {n:>3}d: status=200 rows={len(d):>7} bytes={rec['bytes']:>9} elapsed={rec['elapsed_s']:>5}s "
                  f"pub {span(d, 'publishTime')} [{ok}]")
            prev_rows = len(d)


# --------------------------------------------------------------------------- analyze
FETCH_START, FETCH_END = datetime(2025, 12, 28, tzinfo=UTC), datetime(2026, 2, 3, tzinfo=UTC)
CHUNK_DAYS = 37
DELIVERY_FROM, DELIVERY_TO = date(2026, 1, 2), date(2026, 2, 1)


def cutoff_for(d: date) -> datetime:
    return datetime.combine(d - timedelta(days=1), dtime(9, 30), tzinfo=LONDON).astimezone(UTC)


def part_analyze() -> None:
    head("Loading full fetch window " + f"{FETCH_START:%Y-%m-%d} -> {FETCH_END:%Y-%m-%d}")
    wf = load("WINDFOR", FETCH_START, FETCH_END, CHUNK_DAYS, "full")
    fh = load("FUELHH", FETCH_START, FETCH_END, CHUNK_DAYS, "fullWIND", {"fuelType": "WIND"})

    head("Q9: timestamp format")
    pat = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    for ds, rec_label in (("WINDFOR", f"full_{FETCH_START:%Y%m%d}_{CHUNK_DAYS}d"),
                          ("FUELHH", f"fullWIND_{FETCH_START:%Y%m%d}_{CHUNK_DAYS}d")):
        body = json.loads((RAW / f"{ds}_{rec_label}.json").read_text())["body"]
        bad = [r for r in body for c in ("startTime", "publishTime") if not pat.match(r[c])]
        print(f"  {ds}: {len(body)} rows, timestamps not matching YYYY-MM-DDTHH:MM:SSZ: {len(bad)}")

    head("Q4: FUELHH WIND startTime spacing")
    f = fh.drop_duplicates("startTime").sort_values("startTime")
    print("  distinct gaps between consecutive startTime values:\n",
          f.startTime.diff().dropna().value_counts().to_string())
    print("  minute-of-hour values:", sorted(f.startTime.dt.minute.unique()))
    print("  publishTime - startTime:\n", (fh.publishTime - fh.startTime).value_counts().head(8).to_string())

    head("Q5: WINDFOR startTime spacing")
    gaps = wf.sort_values(["publishTime", "startTime"]).groupby("publishTime").startTime.diff().dropna()
    print("  gaps between consecutive startTime within one publication:\n", gaps.value_counts().to_string())
    print("  minute-of-hour values of startTime:", sorted(wf.startTime.dt.minute.unique()))
    print("  rows per publication:\n", wf.groupby("publishTime").size().describe().to_string())

    head("Q6: WINDFOR publication cadence")
    pubs = sorted(wf.publishTime.unique())
    print(f"  {len(pubs)} distinct publishTime values in {len(set(p.date() for p in pubs))} calendar days "
          f"({pd.Timestamp(pubs[0])} -> {pd.Timestamp(pubs[-1])})")
    per_day = pd.Series([p.date() for p in pubs]).value_counts().sort_index()
    print("  publications per UTC day:\n   ", per_day.value_counts().sort_index().to_dict(), "(count -> n days)")
    print("  distinct HH:MM (UTC):", sorted({p.strftime('%H:%M') for p in pubs}))
    sample = [p for p in pubs if p.date() == date(2026, 1, 14)]
    print(f"  sample day 2026-01-14: {len(sample)} publications:")
    for p in sample:
        sub = wf[wf.publishTime == p]
        print(f"    {p:%Y-%m-%dT%H:%M:%SZ}  rows={len(sub):>3}  startTime {sub.startTime.min():%m-%d %H:%M} -> "
              f"{sub.startTime.max():%m-%d %H:%M}")
    gaps_h = pd.Series(pubs).diff().dropna().value_counts().head(6)
    print("  gaps between consecutive publications:\n", gaps_h.to_string())

    head("Q7: WINDFOR forecast horizon (startTime relative to publishTime, hours)")
    g = wf.assign(off=(wf.startTime - wf.publishTime).dt.total_seconds() / 3600).groupby("publishTime").off
    h = pd.DataFrame({"first": g.min(), "last": g.max()})
    print("  first startTime offset (negative = before publish):\n", h["first"].describe().to_string())
    print("  last startTime offset (= horizon):\n", h["last"].describe().to_string())
    print("  horizon by publication HH:MM (median of last offset):\n",
          h["last"].groupby(h.index.strftime("%H:%M")).median().to_string())
    print(f"  rows with startTime < publishTime: {(wf.startTime < wf.publishTime).sum()} of {len(wf)}")

    head("Q8: duplicates")
    dup = wf[wf.duplicated(["startTime", "publishTime"], keep=False)]
    differ = dup.groupby(["startTime", "publishTime"]).generation.nunique().gt(1).sum() if len(dup) else 0
    print(f"  WINDFOR duplicate (startTime, publishTime) rows: {len(dup)}; groups with differing generation: {differ}")
    print(f"  WINDFOR null generation: {wf.generation.isna().sum()}, negative: {(wf.generation < 0).sum()}, "
          f"min/max: {wf.generation.min()} / {wf.generation.max()}")
    dup = fh[fh.duplicated(["startTime", "publishTime"], keep=False)]
    print(f"  FUELHH WIND duplicate (startTime, publishTime) rows: {len(dup)}")
    per_start = fh.groupby("startTime").agg(pubs=("publishTime", "nunique"), gens=("generation", "nunique"))
    print(f"  FUELHH WIND startTimes with >1 publishTime: {(per_start.pubs > 1).sum()}, "
          f"with >1 distinct generation: {(per_start.gens > 1).sum()}")
    print(f"  FUELHH null generation: {fh.generation.isna().sum()}, min/max: {fh.generation.min()} / {fh.generation.max()}")

    head("Q10: FUELHH completeness (WIND)")
    d0 = datetime.combine(DELIVERY_FROM, dtime(0), tzinfo=UTC)
    d1 = datetime.combine(DELIVERY_TO + timedelta(days=1), dtime(0), tzinfo=UTC)
    expected = pd.date_range(d0, d1, freq="30min", inclusive="left", tz="UTC")
    have = set(fh.startTime)
    missing = [t for t in expected if t not in have]
    print(f"  delivery window {DELIVERY_FROM} -> {DELIVERY_TO} inclusive: expected {len(expected)} half-hours "
          f"({len(expected) // 48} days x 48), present {len(expected) - len(missing)}, missing {len(missing)}")
    if missing:
        print("  missing startTimes:", [t.strftime('%m-%d %H:%M') for t in missing][:30])
    print("  sample day 2026-01-14: rows =", int(((fh.startTime >= datetime(2026, 1, 14, tzinfo=UTC)) &
                                                  (fh.startTime < datetime(2026, 1, 15, tzinfo=UTC))).sum()
                                                 - 0), "(incl. duplicates if any)")
    print("  settlementPeriod range on 2026-01-14:",
          fh[fh.settlementDate == "2026-01-14"].settlementPeriod.agg(["min", "max", "nunique"]).to_dict())
    print("  FUELHH generation stats over delivery window (MW):\n",
          fh[(fh.startTime >= d0) & (fh.startTime < d1)].generation.describe().round(0).to_string())

    head("WINDFOR target coverage over the delivery window (hourly index)")
    hexp = pd.date_range(d0, d1, freq="1h", inclusive="left", tz="UTC")
    wt = set(wf.startTime)
    hmiss = [t for t in hexp if t not in wt]
    print(f"  expected {len(hexp)} hourly targets, any-vintage present {len(hexp) - len(hmiss)}, missing {len(hmiss)}")

    head("Q6b: does a meaningful 'latest forecast at or before the cutoff' exist? (per delivery day)")
    rows = []
    for i in range((DELIVERY_TO - DELIVERY_FROM).days + 1):
        D = DELIVERY_FROM + timedelta(days=i)
        cut = cutoff_for(D)
        day0 = datetime.combine(D, dtime(0), tzinfo=UTC)
        cand = wf[wf.publishTime <= cut]
        if cand.empty:
            rows.append({"D": D, "cutoff": cut, "vintage": None})
            continue
        v_t = cand.publishTime.max()
        v = cand[cand.publishTime == v_t]
        tgt = v[(v.startTime >= day0) & (v.startTime < day0 + timedelta(days=1))]
        nxt = wf.publishTime[wf.publishTime > cut].min()
        lead = (tgt.startTime - v_t).dt.total_seconds() / 3600
        rows.append({"D": D, "cutoff": cut.strftime("%m-%d %H:%M"), "vintage": v_t.strftime("%m-%d %H:%M"),
                     "age_h": round((cut - v_t).total_seconds() / 3600, 2), "targets_of_24": len(tgt),
                     "lead_min_h": lead.min() if len(tgt) else None, "lead_max_h": lead.max() if len(tgt) else None,
                     "next_pub_after_cutoff": nxt.strftime("%m-%d %H:%M") if pd.notna(nxt) else None})
    t = pd.DataFrame(rows)
    print(t.to_string(index=False))
    print("\n  targets_of_24 value counts:", t.targets_of_24.value_counts().to_dict())
    print("  vintage HH:MM used:", t.vintage.str[-5:].value_counts().to_dict())
    print("  vintage age at cutoff (h):", t.age_h.describe().round(2).to_dict())


# --------------------------------------------------------------------------- align
def part_align() -> None:
    head("Convention check (diagnostic only, NOT accuracy reporting): what does a WINDFOR startTime T cover?")
    wf = load("WINDFOR", FETCH_START, FETCH_END, CHUNK_DAYS, "full")
    fh = load("FUELHH", FETCH_START, FETCH_END, CHUNK_DAYS, "fullWIND")
    odd = fh[(fh.publishTime - fh.startTime) != pd.Timedelta(minutes=30)]
    print("  FUELHH rows whose publishTime - startTime != 30 min:")
    print(odd[["startTime", "publishTime", "generation"]].to_string(index=False))
    act = fh.set_index("startTime").generation
    # nowcast: for each target T use the most recent forecast with publishTime <= T (lead >= 0, smallest)
    w = wf[wf.startTime >= wf.publishTime].sort_values(["startTime", "publishTime"]).groupby("startTime").tail(1)
    w = w[(w.startTime >= datetime(2026, 1, 2, tzinfo=UTC)) & (w.startTime < datetime(2026, 2, 2, tzinfo=UTC))]
    print(f"  nowcast sample: {len(w)} hourly targets, lead hours {((w.startTime - w.publishTime).dt.total_seconds() / 3600).describe()[['min','50%','max']].round(2).to_dict()}")
    h = pd.Timedelta(minutes=30)
    cands = {
        "hour beginning T  : mean(S=T, S=T+30)": lambda T: (act.get(T), act.get(T + h)),
        "hour ending T     : mean(S=T-60, S=T-30)": lambda T: (act.get(T - 2 * h), act.get(T - h)),
        "centred on T      : mean(S=T-30, S=T)": lambda T: (act.get(T - h), act.get(T)),
        "point S=T only": lambda T: (act.get(T), act.get(T)),
    }
    for name, fn in cands.items():
        diffs = []
        for T, g in zip(w.startTime, w.generation):
            a, b = fn(T)
            if a is not None and b is not None and a == a and b == b:
                diffs.append(abs(g - (a + b) / 2))
        print(f"  {name:<44} n={len(diffs)} mean|forecast-actual| = {sum(diffs) / len(diffs):7.1f} MW")

    # level / scope check on the hour-beginning alignment: is the gap a constant offset or noise?
    ab = pd.Series({T: (act.get(T) + act.get(T + h)) / 2 for T in w.startTime if T in act and (T + h) in act})
    f = w.set_index("startTime").generation.reindex(ab.index)
    err = f - ab
    print(f"  level check (hour-beginning, nowcast leads): mean forecast={f.mean():.0f} MW, mean actual={ab.mean():.0f} MW, "
          f"mean(f-a)={err.mean():.0f} MW, std(f-a)={err.std():.0f} MW, corr={f.corr(ab):.3f}")
    print(f"  ratio mean forecast / mean actual = {f.mean() / ab.mean():.3f}; "
          f"mean|f-a| after removing mean offset = {(err - err.mean()).abs().mean():.0f} MW")


# --------------------------------------------------------------------------- burst
def part_burst() -> None:
    head("Q12: rate limiting. Burst of 15 uncached tiny requests, no pause")
    global PAUSE_S
    old, PAUSE_S = PAUSE_S, 0
    out = []
    for i in range(15):
        s = datetime(2026, 1, 20, i, tzinfo=UTC)
        rec = get("WINDFOR", {"publishDateTimeFrom": iso(s), "publishDateTimeTo": iso(s + timedelta(minutes=30))},
                  f"burst_{i:02d}")
        out.append((rec["status"], rec["elapsed_s"], rec["headers"]))
    PAUSE_S = old
    print("  statuses:", [o[0] for o in out])
    print("  elapsed (s):", [o[1] for o in out])
    print("  rate-limit related headers seen:", {k for o in out for k in o[2] if "limit" in k.lower() or "retry" in k.lower()} or "none")
    bad = [r for r in LOG if r["status"] != 200]
    print(f"  non-200 responses in network log this run: {len(bad)}")
    print(f"  network calls this run: {len(LOG)} (0 means everything was served from cache)")


PARTS = {"sample": part_sample, "params": part_params, "ladder": part_ladder,
         "analyze": part_analyze, "align": part_align, "burst": part_burst}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name, fn in PARTS.items():
        if which in ("all", name):
            fn()
    print(f"\n[network calls this run: {len(LOG)}; statuses: {sorted({r['status'] for r in LOG})}]")
