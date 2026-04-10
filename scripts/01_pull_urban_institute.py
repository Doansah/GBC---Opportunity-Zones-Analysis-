"""
01_pull_urban_institute.py

Filter the Urban Institute OZ Designation Tool CSV to Maryland's 451 eligible tracts.
Adds a short classification label and saves the backbone dataset.

Inputs:  UrbanInstitute_OZDesignationTool_3_9_2026_0.csv  (project root)
Outputs: data/raw/urban_institute_oz_tool.csv
         data/processed/md_tracts_base.csv
"""

import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_SRC = ROOT / "UrbanInstitute_OZDesignationTool_3_9_2026_0.csv"
RAW_DEST = ROOT / "data" / "raw" / "urban_institute_oz_tool.csv"
PROCESSED_DEST = ROOT / "data" / "processed" / "md_tracts_base.csv"

# ── 1. Copy raw file into data/raw/ ──────────────────────────────────────────
RAW_DEST.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(RAW_SRC, RAW_DEST)
print(f"Copied raw CSV -> {RAW_DEST}")

# ── 2. Load and filter to Maryland ───────────────────────────────────────────
df = pd.read_csv(RAW_DEST, dtype={"geoid": str})
print(f"Total rows (national): {len(df):,}")

md = df[df["state"] == "Maryland"].copy()
print(f"Maryland rows: {len(md)}")
assert len(md) == 451, f"Expected 451 Maryland tracts, got {len(md)}"

# ── 3. Zero-pad geoid to 11 characters ───────────────────────────────────────
md["geoid"] = md["geoid"].str.strip().str.zfill(11)
assert md["geoid"].str.len().eq(11).all(), "Some geoids are not 11 chars"

# ── 4. Add short classification label ────────────────────────────────────────
LABEL_MAP = {
    "More likely to attract OZ investment, with larger impact": "Goldilocks",
    "Likely to attract capital even without OZ designation": "Already Attractive",
    "Less likely to attract OZ investment": "Less Likely",
}
md["classification"] = md["oztoolclassification"].map(LABEL_MAP)
unmapped = md["classification"].isna().sum()
if unmapped:
    print(f"WARNING: {unmapped} rows had unrecognised oztoolclassification values:")
    print(md.loc[md["classification"].isna(), "oztoolclassification"].unique())

print("\nClassification counts:")
print(md["classification"].value_counts())

# ── 5. Save ───────────────────────────────────────────────────────────────────
PROCESSED_DEST.parent.mkdir(parents=True, exist_ok=True)
md.to_csv(PROCESSED_DEST, index=False)
print(f"\nSaved Maryland base table -> {PROCESSED_DEST}")
print(f"Columns: {list(md.columns)}")
