"""
06_aggregate_property_stats.py

Aggregate Baltimore City parcel-level SDAT data to census tract level.
Derives the development-capacity and market metrics used for scoring.

Input:  data/raw/baltimore_real_property.csv  (must have 'geoid' column)
Output: data/processed/baltimore_tract_property_stats.csv
"""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
IN_PATH = ROOT / "data" / "raw" / "baltimore_real_property.csv"
OUT_PATH = ROOT / "data" / "processed" / "baltimore_tract_property_stats.csv"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

CUTOFF_YEAR = 2023  # for "recent" sales (last 3 years from ~2026)

# Actual field name mapping from dmxOwnership:
#   FULLCASH  = total assessed value (CURRVAL equivalent)
#   DHCDUSE1  = land use code (DESCLU equivalent)
#   VACIND    = vacant indicator
#   OWNMDE    = ownership mode ('Y'=owner-occupied / 'F'=non-owner)

# ── Load ──────────────────────────────────────────────────────────────────────
print(f"Loading {IN_PATH} ...")
df = pd.read_csv(IN_PATH, dtype=str, low_memory=False)
print(f"  {len(df):,} rows, {len(df.columns)} columns")

# Drop rows with no tract assignment
df = df.dropna(subset=["geoid"])
print(f"  {len(df):,} rows with a geoid")

# ── Cast numeric columns ──────────────────────────────────────────────────────
# Handle both original expected names and actual names from the service
VALUE_COL = "FULLCASH" if "FULLCASH" in df.columns else "CURRVAL"
for col in ["CURRLAND", "CURRIMPR", VALUE_COL, "SALEPRIC"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# Parse sale date — SALEDATE_good is a Unix timestamp (ms) from the service
if "SALEDATE_good" in df.columns:
    ts = pd.to_numeric(df["SALEDATE_good"], errors="coerce")
    df["sale_year"] = pd.to_datetime(ts, unit="ms", errors="coerce").dt.year
elif "SALEDATE" in df.columns:
    df["sale_year"] = pd.to_datetime(df["SALEDATE"], errors="coerce", infer_datetime_format=True).dt.year

# ── Derived per-parcel fields ─────────────────────────────────────────────────
# land_to_value_ratio: only meaningful when total value > 0
fullcash = df[VALUE_COL] if VALUE_COL in df.columns else pd.Series(np.nan, index=df.index)
df["lv_ratio"] = np.where(
    fullcash.notna() & (fullcash > 0),
    df["CURRLAND"].fillna(0) / fullcash,
    np.nan,
)

# Vacancy flag: VACIND is 'Y' or use code contains 'Vacant'
use_code = df.get("DHCDUSE1", pd.Series("", index=df.index)).fillna("")
propdesc = df.get("PROPDESC", pd.Series("", index=df.index)).fillna("").str.upper()
vacind = df.get("VACIND", pd.Series("", index=df.index)).fillna("").str.upper()
df["is_vacant"] = (vacind == "Y") | (df["CURRIMPR"].fillna(1) == 0)

# Recent sale (last 3 years)
df["is_recent_sale"] = df.get("sale_year", pd.Series(dtype=float)).ge(CUTOFF_YEAR)

# Use group: USEGROUP from the service ('R'=residential, 'C'=commercial, 'I'=industrial)
usegroup = df.get("USEGROUP", pd.Series("", index=df.index)).fillna("").str.strip().str.upper()
df["is_residential"] = usegroup.str.startswith("R") | propdesc.str.contains("RESID", na=False)
# OWNMDE: 'Y' or 'H' = homestead/owner, 'F' = non-owner, etc.
ownmde = df.get("OWNMDE", pd.Series("", index=df.index)).fillna("").str.strip().str.upper()
df["is_owner_occ"] = ownmde.isin(["Y", "H"])

df["is_commercial"] = usegroup.str.startswith("C") | propdesc.str.contains("COMMERC|RETAIL|OFFICE|HOTEL", na=False)
df["is_industrial"] = usegroup.str.startswith("I") | propdesc.str.contains("INDUSTR|MANUFACTUR|WAREHOUSE|STORAGE", na=False)

# ── Aggregate to tract level ──────────────────────────────────────────────────
print("Aggregating to tract level…")

agg = df.groupby("geoid").agg(
    total_parcels=("geoid", "count"),
    land_to_value_ratio=("lv_ratio", "mean"),
    vacancy_proxy=("is_vacant", "mean"),
    market_activity_count=("is_recent_sale", "sum"),
    median_sale_price=("SALEPRIC", lambda s: s[s > 0].median() if (s > 0).any() else np.nan),
    owner_occupancy_rate=("is_owner_occ", lambda s: s.sum() / max((df.loc[s.index, "is_residential"].sum()), 1)),
    pct_residential=("is_residential", "mean"),
    pct_commercial=("is_commercial", "mean"),
    pct_industrial=("is_industrial", "mean"),
    assessed_value_per_parcel=(VALUE_COL, "mean"),
).reset_index()

print(f"  {len(agg)} tracts aggregated")

# Verify owner_occupancy_rate is bounded
agg["owner_occupancy_rate"] = agg["owner_occupancy_rate"].clip(0, 1)

agg.to_csv(OUT_PATH, index=False)
print(f"Saved -> {OUT_PATH}")
print(agg.describe())
