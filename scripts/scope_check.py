"""Validation, not part of the app: is the WINDFOR vs FUELHH offset a scope difference or a bug?

Compares both against independent public sources (NESO embedded wind, Elexon AGWS). Needs network.
Run from the repository root:  backend/.venv/bin/python -I scripts/scope_check.py  (Scripts\ on Windows)
Findings are recorded in docs/ASSUMPTIONS.md section 8.2."""
import json
import sys
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

sys.path.insert(0, "backend")
from app import config, storage  # noqa: E402

RID = "8a4a771c-3929-4e56-93ad-cdf13219dea5"  # NESO Historic Demand Data 2026
sql = (
    'SELECT "SETTLEMENT_DATE","SETTLEMENT_PERIOD","EMBEDDED_WIND_GENERATION",'
    '"EMBEDDED_WIND_CAPACITY","ND","TSD" '
    f'FROM "{RID}" WHERE "SETTLEMENT_DATE" >= \'2026-01-02\' AND "SETTLEMENT_DATE" <= \'2026-02-01T23:59:59\' '
    'ORDER BY "SETTLEMENT_DATE","SETTLEMENT_PERIOD" LIMIT 5000'
)
url = "https://api.neso.energy/api/3/action/datastore_search_sql?sql=" + urllib.parse.quote(sql)
neso = pd.DataFrame(json.load(urllib.request.urlopen(url, timeout=60))["result"]["records"])
neso["date"] = pd.to_datetime(neso["SETTLEMENT_DATE"]).dt.date
for c in ("EMBEDDED_WIND_GENERATION", "EMBEDDED_WIND_CAPACITY", "ND", "TSD"):
    neso[c] = pd.to_numeric(neso[c])
print(f"NESO rows: {len(neso)} (expect 1488); embedded wind capacity {neso.EMBEDDED_WIND_CAPACITY.min():.0f}-{neso.EMBEDDED_WIND_CAPACITY.max():.0f} MW")

agws_url = (
    "https://data.elexon.co.uk/bmrs/api/v1/datasets/AGWS/stream"
    "?publishDateTimeFrom=2026-01-01T00:00:00Z&publishDateTimeTo=2026-02-03T00:00:00Z"
)
ag = pd.DataFrame(json.load(urllib.request.urlopen(agws_url, timeout=90)))
ag["startTime"] = pd.to_datetime(ag["startTime"], utc=True)
ag["publishTime"] = pd.to_datetime(ag["publishTime"], utc=True)
print("AGWS rows", len(ag), "| psrTypes", sorted(ag.psrType.unique()), "| businessTypes", sorted(ag.businessType.unique()))
ag = ag[ag.psrType.isin(["Wind Onshore", "Wind Offshore"])]
# keep the latest publication per (startTime, psrType)
ag = ag.sort_values("publishTime").groupby(["startTime", "psrType"]).tail(1)
agt = ag.groupby("startTime").quantity.sum()  # onshore + offshore, half-hourly MW

a, f = storage.load_frames(config.DB_PATH)
lo, hi = pd.Timestamp("2026-01-02", tz="UTC"), pd.Timestamp("2026-02-02", tz="UTC")
fh = a.set_index("start_time").generation_mw
fh = fh[(fh.index >= lo) & (fh.index < hi)]
agt = agt[(agt.index >= lo) & (agt.index < hi)]
# NESO settlement period p of date d starts at d 00:00 UTC + (p-1)*30min (GMT in January)
neso["start"] = pd.to_datetime(neso["SETTLEMENT_DATE"]).dt.tz_localize("UTC") + pd.to_timedelta((neso.SETTLEMENT_PERIOD - 1) * 30, unit="m")
emb = neso.set_index("start").EMBEDDED_WIND_GENERATION

d = pd.DataFrame({"fuelhh": fh, "agws": agt, "embedded": emb}).dropna()
print(f"\nhalf-hourly joined rows: {len(d)}")
print("means (MW): FUELHH %.0f | AGWS %.0f | NESO embedded %.0f | FUELHH+embedded %.0f" % (d.fuelhh.mean(), d.agws.mean(), d.embedded.mean(), (d.fuelhh + d.embedded).mean()))
print("maxima (MW): FUELHH %.0f | AGWS %.0f | FUELHH+embedded %.0f" % (d.fuelhh.max(), d.agws.max(), (d.fuelhh + d.embedded).max()))
print("FUELHH vs AGWS: corr %.4f, mean diff %.0f MW" % (np.corrcoef(d.fuelhh, d.agws)[0, 1], (d.agws - d.fuelhh).mean()))

# WINDFOR short-lead forecast on the same hours
w = f[(f.start_time >= lo) & (f.start_time < hi)]
nc = w[w.publish_time <= w.start_time].sort_values(["start_time", "publish_time"]).groupby("start_time").tail(1).set_index("start_time").generation_mw
hh = d.copy()
hh["hour"] = hh.index.floor("h")
h = hh.groupby("hour").agg(fuelhh=("fuelhh", "mean"), agws=("agws", "mean"), emb=("embedded", "mean"), n=("fuelhh", "size"))
h = h[h.n == 2].join(nc.rename("windfor"), how="inner")
h["fuelhh_plus_emb"] = h.fuelhh + h.emb
print(f"\nhourly joined rows: {len(h)}; WINDFOR (nowcast) mean {h.windfor.mean():.0f}")
for name in ("fuelhh", "agws", "fuelhh_plus_emb"):
    e = h.windfor - h[name]
    print(f"WINDFOR minus {name:16s}: mean {e.mean():7.0f} MW | MAE {e.abs().mean():6.0f} | std {e.std():6.0f} | corr {np.corrcoef(h.windfor, h[name])[0, 1]:.4f} | ratio of means {h.windfor.mean() / h[name].mean():.3f}")

print("\n=== daily figures: high-wind day and low-wind day (daily mean MW) ===")
h["day"] = h.index.date
dd = h.groupby("day").mean(numeric_only=True)[["fuelhh", "agws", "emb", "fuelhh_plus_emb", "windfor"]].round(0)
for day in (pd.Timestamp("2026-01-27").date(), pd.Timestamp("2026-01-08").date()):
    print(day, dd.loc[day].to_dict())
print("\nNESO embedded wind capacity on those days:", neso[neso.date.isin([pd.Timestamp('2026-01-27').date(), pd.Timestamp('2026-01-08').date()])].groupby("date").EMBEDDED_WIND_CAPACITY.first().to_dict())


# ---- day-ahead (primary cutoff) error against alternative "actual" definitions
from datetime import timedelta  # noqa: E402
from app import align, metrics  # noqa: E402

base = align.build_aligned_table(a, f, config.DELIVERY_FROM, config.DELIVERY_TO, config.CUTOFFS["epex60"])
hh2 = pd.DataFrame({"fuelhh": fh, "agws": agt, "emb": emb}).dropna()
hh2["hour"] = hh2.index.floor("h")
hourly = hh2.groupby("hour").mean()
rows = []
for label, series in (("FUELHH only (as in the app)", hourly.fuelhh), ("FUELHH + NESO embedded wind", hourly.fuelhh + hourly.emb), ("Elexon AGWS national wind", hourly.agws)):
    t = base.copy()
    t["actual_mw"] = t.target_time.map(series)
    t["error"] = t.forecast_mw - t.actual_mw
    t["abs_error"] = t.error.abs()
    t["status"] = np.where(t.actual_mw.notna(), "ok", "missing_actual")
    h = metrics.headline(t)
    rows.append((label, h["n_valid"], h["mae_mw"], h["rmse_mw"], h["bias_mw"], h["nmae_pct"], h["debiased_mae_mw"], h["mean_actual_mw"]))
print("\nDAY-AHEAD (09:20 cutoff) error against different definitions of 'actual wind':")
print(pd.DataFrame(rows, columns=["actual definition", "n", "MAE", "RMSE", "bias", "nMAE%", "debiasedMAE", "mean actual"]).round(1).to_string(index=False))
