"""
09_apply_filters.py

Apply Stage 1 hard filters to the master tract table.

Filter OUT "unviable":        jobs_2022 < 200 AND povrate_2024 > 0.45 AND has_any_permits == 0
Filter OUT "already attractive": median_hhincome > metro_median AND median_homevalue > 75th pct

Everything else advances to scoring.

Input:  data/processed/md_tracts_master.csv
Output: data/processed/md_tracts_filtered.csv
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
IN_PATH = ROOT / "data" / "processed" / "md_tracts_master.csv"
OUT_PATH = ROOT / "data" / "processed" / "md_tracts_filtered.csv"

# ── Load ──────────────────────────────────────────────────────────────────────
print(f"Loading {IN_PATH}…")
df = pd.read_csv(IN_PATH, dtype={"geoid": str})
print(f"  {len(df)} tracts")
assert len(df) == 451

# ── Reference thresholds ──────────────────────────────────────────────────────
metro_median_income = df["median_hhincome_2024"].median()
top_quartile_homevalue = df["median_homevalue_2024"].quantile(0.75)

print(f"\nReference thresholds:")
print(f"  Metro median household income: ${metro_median_income:,.0f}")
print(f"  Top quartile home value (75th pct): ${top_quartile_homevalue:,.0f}")

# ── Stage 1 filter logic ──────────────────────────────────────────────────────
# Unviable: low jobs AND extreme poverty AND zero permit activity
# Note: for non-Baltimore tracts, has_any_permits == 0 because we have no data.
# We only apply this filter if jobs_2022 and povrate_2024 also qualify.
unviable_mask = (
    (df["jobs_2022"].fillna(0) < 200) &
    (df["povrate_2024"].fillna(0) > 0.45) &
    (df["has_any_permits"].fillna(0) == 0)
)

# Already attractive: income above metro median AND home values in top quartile
already_attractive_mask = (
    (df["median_hhincome_2024"] > metro_median_income) &
    (df["median_homevalue_2024"] > top_quartile_homevalue)
)

# Assign labels
df["stage1_result"] = "Advances to Scoring"
df.loc[unviable_mask, "stage1_result"] = "Eliminated — Unviable"
df.loc[already_attractive_mask & ~unviable_mask, "stage1_result"] = "Eliminated — Already Attractive"

# ── Summary ───────────────────────────────────────────────────────────────────
counts = df["stage1_result"].value_counts()
print(f"\nStage 1 results:")
for label, n in counts.items():
    print(f"  {label}: {n}")

assert counts.sum() == 451, "Row count mismatch after filtering"

# ── Save ──────────────────────────────────────────────────────────────────────
df.to_csv(OUT_PATH, index=False)
print(f"\nSaved -> {OUT_PATH}")

advances = df[df["stage1_result"] == "Advances to Scoring"]
print(f"\n{len(advances)} tracts advance to scoring.")
print(f"Classification breakdown among advancing tracts:")
print(advances["classification"].value_counts())
