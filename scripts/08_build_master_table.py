"""
08_build_master_table.py

Join all data sources into a single row-per-tract master table for Maryland's
451 eligible OZ tracts.

Also computes incentive zone stackability by spatially intersecting tract
centroids with the three iMAP incentive zone layers.

Inputs:
  data/processed/md_tracts_base.csv
  data/processed/baltimore_tract_property_stats.csv
  data/processed/baltimore_tract_permit_stats.csv
  data/raw/imap_incentive_zones/enterprise_zones.geojson
  data/raw/imap_incentive_zones/sustainable_communities.geojson
  data/raw/imap_incentive_zones/rise_zones.geojson
  census_tract_shape_files/tl_2025_24_tract.shp

Output:
  data/processed/md_tracts_master.csv
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

BASE_CSV = ROOT / "data" / "processed" / "md_tracts_base.csv"
PROP_CSV = ROOT / "data" / "processed" / "baltimore_tract_property_stats.csv"
PERM_CSV = ROOT / "data" / "processed" / "baltimore_tract_permit_stats.csv"
SHP_PATH = ROOT / "census_tract_shape_files" / "tl_2025_24_tract.shp"

IMAP_DIR = ROOT / "data" / "raw" / "imap_incentive_zones"
INCENTIVE_FILES = {
    "enterprise_zones": IMAP_DIR / "enterprise_zones.geojson",
    "sustainable_communities": IMAP_DIR / "sustainable_communities.geojson",
    "rise_zones": IMAP_DIR / "rise_zones.geojson",
}

OUT_PATH = ROOT / "data" / "processed" / "md_tracts_master.csv"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── 1. Load base table ────────────────────────────────────────────────────────
print("Loading base table…")
base = pd.read_csv(BASE_CSV, dtype={"geoid": str})
base["geoid"] = base["geoid"].str.zfill(11)
print(f"  {len(base)} Maryland tracts")
assert len(base) == 451, f"Expected 451 MD tracts, got {len(base)}"

# ── 2. Left-join property stats ───────────────────────────────────────────────
if PROP_CSV.exists():
    prop = pd.read_csv(PROP_CSV, dtype={"geoid": str})
    prop["geoid"] = prop["geoid"].str.zfill(11)
    base = base.merge(prop, on="geoid", how="left")
    print(f"  Joined property stats: {prop['geoid'].nunique()} tracts had data")
else:
    print(f"  WARNING: {PROP_CSV} not found — property columns will be NaN")

# ── 3. Left-join permit stats ─────────────────────────────────────────────────
if PERM_CSV.exists():
    perm = pd.read_csv(PERM_CSV, dtype={"geoid": str})
    perm["geoid"] = perm["geoid"].str.zfill(11)
    base = base.merge(perm, on="geoid", how="left")
    print(f"  Joined permit stats: {perm['geoid'].nunique()} tracts had data")
else:
    print(f"  WARNING: {PERM_CSV} not found — permit columns will be NaN")

# ── 4. Compute stackability via spatial intersection ──────────────────────────
print("\nComputing incentive zone stackability…")

# Load tract geometries for the 451 MD eligible tracts
tracts_geo = gpd.read_file(SHP_PATH)
geoid_col = next(c for c in tracts_geo.columns if c.upper() == "GEOID")
tracts_geo = tracts_geo.rename(columns={geoid_col: "geoid"})
tracts_geo["geoid"] = tracts_geo["geoid"].str.zfill(11)
tracts_geo = tracts_geo.to_crs("EPSG:4326")

# Filter to just our 451 eligible tracts
eligible_geoids = set(base["geoid"].unique())
tracts_geo = tracts_geo[tracts_geo["geoid"].isin(eligible_geoids)][["geoid", "geometry"]].copy()
print(f"  Tract geometries loaded: {len(tracts_geo)}")

# Use tract centroids for the intersection check (fast, sufficient for our purposes)
tracts_geo["centroid"] = tracts_geo.geometry.centroid
centroids = tracts_geo.set_geometry("centroid")[["geoid", "centroid"]].rename(columns={"centroid": "geometry"})

stackability_counts = pd.Series(0, index=tracts_geo["geoid"], name="stackability_count")

for layer_name, filepath in INCENTIVE_FILES.items():
    if not filepath.exists():
        print(f"  WARNING: {filepath} not found — skipping {layer_name}")
        continue

    zone_gdf = gpd.read_file(filepath)
    if zone_gdf.empty:
        print(f"  {layer_name}: 0 features — skipping")
        continue

    zone_gdf = zone_gdf.to_crs("EPSG:4326")
    zone_union = zone_gdf.geometry.union_all()

    # Check which tract centroids fall within this zone layer's union polygon
    hits = centroids["geometry"].within(zone_union)
    matched_geoids = centroids.loc[hits, "geoid"]
    stackability_counts[matched_geoids] += 1
    print(f"  {layer_name}: {hits.sum()} tracts intersect")

stackability_df = stackability_counts.reset_index()
stackability_df.columns = ["geoid", "stackability_count"]
stackability_df["has_stackability"] = (stackability_df["stackability_count"] > 0).astype(int)

base = base.merge(stackability_df, on="geoid", how="left")
base["stackability_count"] = base["stackability_count"].fillna(0).astype(int)
base["has_stackability"] = base["has_stackability"].fillna(0).astype(int)

# ── 5. Fill has_any_permits for non-Baltimore tracts ─────────────────────────
# Non-Baltimore tracts have NaN in permit columns — treat as "no permits data"
if "has_any_permits" in base.columns:
    base["has_any_permits"] = base["has_any_permits"].fillna(0).astype(int)

# ── 6. Save ───────────────────────────────────────────────────────────────────
assert len(base) == 451, f"Master table row count changed! Got {len(base)}"
base.to_csv(OUT_PATH, index=False)
print(f"\nMaster table saved -> {OUT_PATH}")
print(f"  Shape: {base.shape}")
print(f"  Columns: {list(base.columns)}")
print(f"\nStackability distribution:")
print(base["stackability_count"].value_counts().sort_index())
