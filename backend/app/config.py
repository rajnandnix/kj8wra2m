"""Single source of truth for dates, decision cutoffs, URLs and paths.

Nothing else in the codebase may hard-code a date, a cutoff time or a URL.
"""

import os
from dataclasses import dataclass
from datetime import date, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")

# --- Date window -------------------------------------------------------------------------
# Interpretation: purchase decisions are made on D-1 for delivery on D. Decision days are all
# of January 2026, so delivery days run 2 Jan to 1 Feb 2026 inclusive (docs/ASSUMPTIONS.md).
DECISION_FROM = date(2026, 1, 1)
DECISION_TO = date(2026, 1, 31)
DELIVERY_FROM = DECISION_FROM + timedelta(days=1)
DELIVERY_TO = DECISION_TO + timedelta(days=1)

# Forecasts are fetched from this date so every vintage published before the first cutoff exists.
FETCH_FORECAST_FROM = date(2025, 12, 28)

# --- Decision cutoffs (GB day-ahead gate closures, local time on D-1) ---------------------


@dataclass(frozen=True)
class Cutoff:
    key: str
    label: str
    local_time: time
    description: str

    @property
    def display(self) -> str:
        return f"{self.local_time:%H:%M} Europe/London on D-1"


CUTOFFS: dict[str, Cutoff] = {
    c.key: c
    for c in (
        Cutoff(
            "epex60",
            "EPEX 60 min auction",
            time(9, 20),
            "EPEX SPOT GB 60 minute day-ahead auction gate closure. Earliest main GB "
            "day-ahead gate, so the conservative, lookahead-safe choice.",
        ),
        Cutoff(
            "n2ex",
            "N2EX auction",
            time(9, 50),
            "Nord Pool N2EX day-ahead auction gate closure.",
        ),
        Cutoff(
            "epex30",
            "EPEX 30 min auction",
            time(15, 30),
            "EPEX SPOT GB 30 minute day-ahead auction gate closure.",
        ),
    )
}
PRIMARY_CUTOFF = "epex60"

# Deliberate conservatism: a forecast stamped t is treated as in hand only from t + PUBLICATION_LAG,
# and the comparison stays `publishTime + lag <= cutoff`. A forecast stamped 15:30:00 is not on the
# desk of someone submitting into a 15:30:00 gate, so it must not count as available to them.
# WINDFOR publishes at 15:30 UTC, exactly the 15:30 gate closure, so this matters for that one
# cutoff (it selects the 11:30 vintage, not 15:30). The data cannot show true availability
# latency, so one minute is the smallest step that excludes a same-instant publication.
PUBLICATION_LAG = timedelta(minutes=1)

# --- Analysis parameters -----------------------------------------------------------------
# Demo days. The default is a typical day where the band works; the sensitivity example is the day
# where a later gate helps most (the 11:30 forecast revised the 07:30 to 09:30 one down sharply).
DEFAULT_DELIVERY_DATE = date(2026, 1, 9)
SENSITIVITY_EXAMPLE_DATE = date(2026, 1, 28)

INTERVAL_HOURS = 1.0  # evaluation resolution: WINDFOR is hourly
PERCENTILES = (10, 50, 90)
# Generation-level buckets on actual MW. The brief's 0-2-4 GW example is far below the
# January range (1.7-17.8 GW), so these edges are set for this data.
LEVEL_BUCKET_EDGES_MW = (0, 6000, 10000, 14000, float("inf"))
HISTOGRAM_BIN_MW = 500
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20260101

# --- Elexon BMRS ---------------------------------------------------------------------------
ELEXON_BASE = "https://data.elexon.co.uk/bmrs/api/v1/datasets"
FUELHH_URL = f"{ELEXON_BASE}/FUELHH/stream"
WINDFOR_URL = f"{ELEXON_BASE}/WINDFOR/stream"
FUEL_TYPE = "WIND"
FETCH_CHUNK_DAYS = 7

# --- Paths -----------------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("WIND_DATA_DIR", REPO_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "app.db"


def cutoff_by_key(key: str | None) -> Cutoff:
    k = key or PRIMARY_CUTOFF
    if k not in CUTOFFS:
        raise KeyError(f"unknown cutoff '{k}', expected one of {sorted(CUTOFFS)}")
    return CUTOFFS[k]
