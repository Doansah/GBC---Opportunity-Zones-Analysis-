"""
10_score_tracts.py

Stage 2: Weighted composite scoring of tracts that advanced through Stage 1 filters.

Scoring weights (must sum to 1.0):
  Investment Viability (55%):
    - job_density_score        30%   minmax(jobs_2022)
    - vacancy_rate_score       10%   minmax(vacancyrate_2024)
    - home_value_inv_score     10%   inverse_minmax(median_homevalue_2024)
    - ownership_inv_score       5%   inverse_minmax(pct_own_2024)

  Community Need (45%):
    - poverty_score            18%   bell curve peaking at 0.28, penalty >0.45
    - income_inv_score         12%   inverse_minmax(median_hhincome_2024)
    - unemployment_score        8%   minmax(unemprate_2024)
    - education_inv_score       7%   inverse_minmax(pct_ba_2024)

All 8 inputs are ACS-derived variables present for all 451 MD tracts (zero nulls).
Baltimore-only data (SDAT parcels, permits) and stackability remain in the output
file as supplementary display columns but do not feed the composite score.

Input:  data/processed/md_tracts_filtered.csv
Output: data/output/scored_tracts.csv
"""

from pathlib import Path

import numpy as np
import pandas as pd

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


def poverty_score(pov: pd.Series) -> pd.Series:
    """Bell-curve score peaking at ~28% poverty; penalty above 45%."""
    pov = pov.fillna(0.25)
    score = 1 - np.abs(pov - 0.28) / 0.28
    score = score.clip(0, 1)
    score = np.where(pov > 0.45, score * 0.5, score)
    return pd.Series(score, index=pov.index)


# ── Load ──────────────────────────────────────────────────────────────────────
print(f"Loading {IN_PATH}…")
df = pd.read_csv(IN_PATH, dtype={"geoid": str})
print(f"  Total rows: {len(df)}")

# Work on advancing tracts only; append eliminated tracts at the end
advancing = df[df["stage1_result"] == "Advances to Scoring"].copy()
eliminated = df[df["stage1_result"] != "Advances to Scoring"].copy()
print(f"  Advancing tracts: {len(advancing)}")
print(f"  Eliminated tracts: {len(eliminated)}")

# ── NULL GUARD ────────────────────────────────────────────────────────────────
# Six of the 8 inputs are guaranteed non-null across all 451 tracts.
# Two (median_homevalue_2024, median_hhincome_2024) can be null in the Urban
# Institute source for tracts with zero owner-occupied units or near-zero
# household counts. Impute these with the advancing-tract median and log every
# affected tract explicitly — no silent imputation.
GUARANTEED_INPUTS = [
    "jobs_2022", "vacancyrate_2024", "pct_own_2024",
    "povrate_2024", "unemprate_2024", "pct_ba_2024",
]
IMPUTABLE_INPUTS = ["median_homevalue_2024", "median_hhincome_2024"]
SCORE_INPUTS = GUARANTEED_INPUTS + IMPUTABLE_INPUTS

# Hard halt if any guaranteed-non-null input has nulls
guaranteed_nulls = advancing[GUARANTEED_INPUTS].isnull().sum()
if guaranteed_nulls.any():
    print("\nERROR — unexpected nulls in guaranteed-complete scoring inputs:")
    print(guaranteed_nulls[guaranteed_nulls > 0])
    raise SystemExit(1)

# Explicit imputation for known-nullable inputs
for col in IMPUTABLE_INPUTS:
    null_rows = advancing[advancing[col].isnull()]
    if len(null_rows) > 0:
        impute_val = advancing[col].median()
        print(f"\nWARNING: {len(null_rows)} advancing tracts have null {col} "
              f"— imputing with advancing-tract median ({impute_val:,.0f}):")
        print(null_rows[["geoid", "county", "classification"]].to_string(index=False))
        advancing[col] = advancing[col].fillna(impute_val)

# Verify zero nulls after imputation
final_nulls = advancing[SCORE_INPUTS].isnull().sum()
if final_nulls.any():
    print("\nERROR — nulls remain after imputation:")
    print(final_nulls[final_nulls > 0])
    raise SystemExit(1)
print("\nNull check passed — all 8 scoring inputs are complete for advancing tracts.")

# ── Sub-scores ────────────────────────────────────────────────────────────────

# 1. Job density (30%) — higher jobs = better investment viability
advancing["job_density_score"]    = minmax(advancing["jobs_2022"])

# 2. Vacancy rate (10%) — higher ACS vacancy = more development capacity
advancing["vacancy_rate_score"]   = minmax(advancing["vacancyrate_2024"])

# 3. Home value inverse (10%) — lower value = more development upside
advancing["home_value_inv_score"] = inverse_minmax(advancing["median_homevalue_2024"])

# 4. Ownership rate inverse (5%) — lower owner-occupancy = more Goldilocks signal
advancing["ownership_inv_score"]  = inverse_minmax(advancing["pct_own_2024"])

# 5. Poverty score (18%) — sweet spot 20-35%; cap extreme distress
advancing["poverty_score"]        = poverty_score(advancing["povrate_2024"])

# 6. Income inverse (12%) — lower income = higher need
advancing["income_inv_score"]     = inverse_minmax(advancing["median_hhincome_2024"])

# 7. Unemployment score (8%) — higher unemployment = higher need
advancing["unemployment_score"]   = minmax(advancing["unemprate_2024"])

# 8. Education inverse (7%) — lower BA attainment = higher need
advancing["education_inv_score"]  = inverse_minmax(advancing["pct_ba_2024"])

# ── Composite score ───────────────────────────────────────────────────────────
WEIGHTS = {
    "job_density_score":    0.30,
    "vacancy_rate_score":   0.10,
    "home_value_inv_score": 0.10,
    "ownership_inv_score":  0.05,
    "poverty_score":        0.18,
    "income_inv_score":     0.12,
    "unemployment_score":   0.08,
    "education_inv_score":  0.07,
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
