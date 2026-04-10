"""
10_score_tracts.py

Stage 2: Weighted composite scoring of tracts that advanced through Stage 1 filters.

Scoring weights (must sum to 1.0):
  Investment Viability (52%):
    - job_density_score        30%
    - development_capacity     12%  (land_to_value_ratio + vacancy_proxy)
    - market_momentum          10%  (permit_trend + median_sale_price_inv)

  Community Need (33%):
    - poverty_score            15%  (moderate distress preferred; extreme penalised)
    - income_score             10%  (inverse — lower income = higher need)
    - unemployment_score        8%

  Stackability (15%):
    - stackability_score       15%

Input:  data/processed/md_tracts_filtered.csv
Output: data/output/scored_tracts.csv
"""

from pathlib import Path

import numpy as np
import pandas as pd
try:
    from sklearn.preprocessing import MinMaxScaler  # noqa: F401
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

ROOT = Path(__file__).resolve().parent.parent
IN_PATH = ROOT / "data" / "processed" / "md_tracts_filtered.csv"
OUT_PATH = ROOT / "data" / "output" / "scored_tracts.csv"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

TARGET_DESIGNATIONS = 113  # governor can designate up to 25% of 451


def minmax(series: pd.Series) -> pd.Series:
    """Normalise a series to [0, 1]; handle all-NaN gracefully."""
    s = series.copy().astype(float)
    lo, hi = s.min(), s.max()
    if pd.isna(lo) or pd.isna(hi) or lo == hi:
        return s.fillna(0.5)  # neutral when no variation
    return (s - lo) / (hi - lo)


def inverse_minmax(series: pd.Series) -> pd.Series:
    """Normalise then invert so that lower raw value = higher score."""
    return 1 - minmax(series)


# ── Load ──────────────────────────────────────────────────────────────────────
print(f"Loading {IN_PATH}…")
df = pd.read_csv(IN_PATH, dtype={"geoid": str})
print(f"  Total rows: {len(df)}")

# Work on advancing tracts only; we'll append eliminated tracts at the end
advancing = df[df["stage1_result"] == "Advances to Scoring"].copy()
eliminated = df[df["stage1_result"] != "Advances to Scoring"].copy()
print(f"  Advancing tracts: {len(advancing)}")
print(f"  Eliminated tracts: {len(eliminated)}")

# ── Sub-scores ────────────────────────────────────────────────────────────────

# 1. Job density (30%) — higher jobs = better investment viability
advancing["job_density_score"] = minmax(advancing["jobs_2022"].fillna(0))

# 2. Development capacity (12%) — average of land_to_value_ratio and vacancy_proxy
#    Both higher = more development potential
lv = minmax(advancing.get("land_to_value_ratio", pd.Series(np.nan, index=advancing.index)).fillna(advancing.get("land_to_value_ratio", pd.Series()).median()))
vac = minmax(advancing.get("vacancy_proxy", pd.Series(np.nan, index=advancing.index)).fillna(0.1))
advancing["dev_capacity_score"] = (lv + vac) / 2

# 3. Market momentum (10%) — permit trend (higher = better) + inverse sale price
#    (lower sale prices relative to peers = more upside / affordability for developers)
pt = minmax(advancing.get("permit_trend", pd.Series(np.nan, index=advancing.index)).fillna(1.0))
sp_inv = inverse_minmax(advancing.get("median_sale_price", pd.Series(np.nan, index=advancing.index)).fillna(advancing.get("median_sale_price", pd.Series()).median()))
advancing["market_momentum_score"] = (pt + sp_inv) / 2

# 4. Poverty score (15%) — sweet spot 20-35%; cap extreme distress
# Map poverty rate to a bell-curve-like score: peak around 0.28 (28%)
def poverty_score(pov: pd.Series) -> pd.Series:
    pov = pov.fillna(0.25)
    # Score declines for very low poverty (less need) and very high poverty (less viable)
    # Peak score at ~28% poverty
    score = 1 - np.abs(pov - 0.28) / 0.28
    score = score.clip(0, 1)
    # Extra penalty for extreme distress (>45%)
    score = np.where(pov > 0.45, score * 0.5, score)
    return pd.Series(score, index=pov.index)

advancing["poverty_score"] = poverty_score(advancing["povrate_2024"])

# 5. Income score (10%) — lower income = higher need
advancing["income_score"] = inverse_minmax(advancing["median_hhincome_2024"])

# 6. Unemployment score (8%) — higher unemployment = higher need
advancing["unemployment_score"] = minmax(advancing["unemprate_2024"].fillna(advancing["unemprate_2024"].median()))

# 7. Stackability score (15%) — 0 to 3 overlapping zones -> normalise to [0,1]
advancing["stackability_score"] = (advancing["stackability_count"].fillna(0) / 3).clip(0, 1)

# ── Composite score ───────────────────────────────────────────────────────────
WEIGHTS = {
    "job_density_score":    0.30,
    "dev_capacity_score":   0.12,
    "market_momentum_score":0.10,
    "poverty_score":        0.15,
    "income_score":         0.10,
    "unemployment_score":   0.08,
    "stackability_score":   0.15,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1.0"

advancing["composite_score"] = sum(
    advancing[col] * w for col, w in WEIGHTS.items()
)

# Rank descending (1 = best)
advancing["rank"] = advancing["composite_score"].rank(ascending=False, method="min", na_option="bottom").astype("Int64")
advancing["recommended"] = (advancing["rank"] <= TARGET_DESIGNATIONS).astype(int)

# ── Combine and save ──────────────────────────────────────────────────────────
eliminated["composite_score"] = np.nan
eliminated["rank"] = np.nan
eliminated["recommended"] = 0

score_cols = list(WEIGHTS.keys()) + ["composite_score", "rank", "recommended"]
for col in score_cols:
    if col not in eliminated.columns:
        eliminated[col] = np.nan

all_tracts = pd.concat([advancing, eliminated], ignore_index=True)
all_tracts = all_tracts.sort_values("rank", na_position="last")

all_tracts.to_csv(OUT_PATH, index=False)
print(f"\nScored tracts saved -> {OUT_PATH}")

# ── Summary ───────────────────────────────────────────────────────────────────
top = advancing.sort_values("rank").head(20)
print(f"\nTop 20 recommended tracts:")
display_cols = ["geoid", "county", "classification", "composite_score", "rank",
                "jobs_2022", "povrate_2024", "stackability_count"]
display_cols = [c for c in display_cols if c in top.columns]
print(top[display_cols].to_string(index=False))

print(f"\nRecommended tracts by classification:")
print(advancing[advancing["recommended"] == 1]["classification"].value_counts())

print(f"\nTotal recommended: {advancing['recommended'].sum()} (target: {TARGET_DESIGNATIONS})")
