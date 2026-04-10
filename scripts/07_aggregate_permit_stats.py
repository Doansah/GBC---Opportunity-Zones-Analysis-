"""
07_aggregate_permit_stats.py

Aggregate Baltimore City building permit data to census tract level.
Derives permit activity metrics used for scoring market momentum.

Input:  data/raw/baltimore_building_permits.csv  (must have 'geoid' column)
Output: data/processed/baltimore_tract_permit_stats.csv
"""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
IN_PATH = ROOT / "data" / "raw" / "baltimore_building_permits.csv"
OUT_PATH = ROOT / "data" / "processed" / "baltimore_tract_permit_stats.csv"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

RECENT_CUTOFF = 2024   # last 2 years (2024-2025 from perspective of 2026)
PRIOR_START = 2021     # prior 3 years (2021-2023)
TOTAL_START = 2021     # "last 5 years" window

# ── Load ──────────────────────────────────────────────────────────────────────
print(f"Loading {IN_PATH} …")
df = pd.read_csv(IN_PATH, dtype=str, low_memory=False)
print(f"  {len(df):,} rows")

if df.empty or "geoid" not in df.columns:
    print("WARNING: permits file is empty or missing geoid column.")
    print("Writing empty permit stats placeholder.")
    empty = pd.DataFrame(columns=[
        "geoid", "permits_total", "permits_new_construction",
        "permits_residential", "permits_commercial",
        "permit_trend", "has_any_permits",
    ])
    empty.to_csv(OUT_PATH, index=False)
    print(f"Saved empty placeholder -> {OUT_PATH}")
    raise SystemExit(0)

# Drop rows with no tract
df = df.dropna(subset=["geoid"])
print(f"  {len(df):,} rows with geoid")

# ── Parse issue_date ──────────────────────────────────────────────────────────
date_col = next((c for c in df.columns if "issue" in c.lower() or "date" in c.lower()), None)
if date_col:
    ts = pd.to_numeric(df[date_col], errors="coerce")
    # ArcGIS returns Unix ms timestamps; try that first, fall back to string parsing
    if ts.notna().sum() > len(df) * 0.5:
        df["issue_date_parsed"] = pd.to_datetime(ts, unit="ms", errors="coerce")
    else:
        df["issue_date_parsed"] = pd.to_datetime(df[date_col], errors="coerce")
    df["issue_year"] = df["issue_date_parsed"].dt.year
else:
    print("WARNING: No date column found in permits — setting issue_year to NaN")
    df["issue_year"] = np.nan

# ── Classify permit types ─────────────────────────────────────────────────────
type_col = next((c for c in df.columns if "type" in c.lower() or "permit_type" in c.lower()), None)
desc_col = next((c for c in df.columns if "desc" in c.lower()), None)
combined_type = ""
if type_col:
    combined_type = df[type_col].fillna("").str.upper()
if desc_col:
    combined_type = combined_type + " " + df[desc_col].fillna("").str.upper()

df["is_new_construction"] = combined_type.str.contains("NEW CONSTRUCT|NEW BUILD|NEW RESIDENTIAL|NEW COMMERCIAL", na=False)
df["is_residential"] = combined_type.str.contains("RESID|HOUSING|DWELLING|SINGLE FAMILY|MULTI FAMILY", na=False)
df["is_commercial"] = combined_type.str.contains("COMMERC|RETAIL|OFFICE|HOTEL|BUSINESS", na=False)

# ── Time windows ─────────────────────────────────────────────────────────────
df_total = df[df["issue_year"].ge(TOTAL_START)]
df_recent = df[df["issue_year"].ge(RECENT_CUTOFF)]
df_prior = df[df["issue_year"].ge(PRIOR_START) & df["issue_year"].lt(RECENT_CUTOFF)]

# ── Aggregate ─────────────────────────────────────────────────────────────────
print("Aggregating to tract level…")

total_agg = df_total.groupby("geoid").agg(
    permits_total=("geoid", "count"),
    permits_new_construction=("is_new_construction", "sum"),
    permits_residential=("is_residential", "sum"),
    permits_commercial=("is_commercial", "sum"),
).reset_index()

recent_agg = df_recent.groupby("geoid").size().rename("permits_recent").reset_index()
prior_agg = df_prior.groupby("geoid").size().rename("permits_prior").reset_index()

agg = total_agg.merge(recent_agg, on="geoid", how="left")
agg = agg.merge(prior_agg, on="geoid", how="left")
agg[["permits_recent", "permits_prior"]] = agg[["permits_recent", "permits_prior"]].fillna(0)

# permit_trend = recent / prior (capped at 5 to avoid division-by-zero inflation)
agg["permit_trend"] = np.where(
    agg["permits_prior"] > 0,
    (agg["permits_recent"] / agg["permits_prior"]).clip(upper=5),
    np.where(agg["permits_recent"] > 0, 5.0, 1.0),  # some activity but no prior = strong trend
)

agg["has_any_permits"] = (agg["permits_total"] > 0).astype(int)

# ── All tracts that appear only in prior/recent but not total window ──────────
# (shouldn't happen but clean up)
agg = agg.drop(columns=["permits_recent", "permits_prior"])

print(f"  {len(agg)} tracts with permit activity")
agg.to_csv(OUT_PATH, index=False)
print(f"Saved -> {OUT_PATH}")
print(agg.describe())
