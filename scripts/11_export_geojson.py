"""
11_export_geojson.py

Merge scored_tracts.csv with census tract geometries and export as GeoJSON
for the interactive site. Carries ALL columns — Baltimore-only supplementary
columns (SDAT parcels, permits) will be null for non-Baltimore tracts; the
site's JavaScript handles conditional display.

Input:  data/output/scored_tracts.csv
        census_tract_shape_files/tl_2025_24_tract.shp
Output: data/output/scored_tracts.geojson   (canonical pipeline output)
        docs/data/scored_tracts.geojson     (copy for GitHub Pages site)
"""

import shutil
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SCORES_CSV = ROOT / "data" / "output" / "scored_tracts.csv"
SHP_PATH   = ROOT / "census_tract_shape_files" / "tl_2025_24_tract.shp"
OUT_GEOJSON = ROOT / "data" / "output" / "scored_tracts.geojson"
SITE_GEOJSON = ROOT / "docs" / "data" / "scored_tracts.geojson"

# ── Load scores ───────────────────────────────────────────────────────────────
print(f"Loading scores from {SCORES_CSV}…")
scores = pd.read_csv(SCORES_CSV, dtype={"geoid": str})
scores["geoid"] = scores["geoid"].str.zfill(11)
print(f"  {len(scores)} rows, {len(scores.columns)} columns")
assert len(scores) == 451, f"Expected 451 rows, got {len(scores)}"

# ── Load tract geometries ─────────────────────────────────────────────────────
print(f"\nLoading shapefile from {SHP_PATH}…")
tracts = gpd.read_file(SHP_PATH)
geoid_col = next(c for c in tracts.columns if c.upper() == "GEOID")
tracts = tracts.rename(columns={geoid_col: "geoid"})
tracts["geoid"] = tracts["geoid"].str.zfill(11)
tracts = tracts.to_crs("EPSG:4326")

# Keep only the 451 eligible MD tracts
eligible = set(scores["geoid"])
tracts = tracts[tracts["geoid"].isin(eligible)][["geoid", "geometry"]].copy()
print(f"  {len(tracts)} eligible tract geometries found")

# ── Merge ─────────────────────────────────────────────────────────────────────
print("\nMerging scores with geometries…")
merged = tracts.merge(scores, on="geoid", how="inner")
gdf = gpd.GeoDataFrame(merged, geometry="geometry", crs="EPSG:4326")

if len(gdf) != 451:
    missing = eligible - set(gdf["geoid"])
    print(f"WARNING: {451 - len(gdf)} tracts have no geometry match:")
    for g in sorted(missing):
        print(f"  {g}")
    print("Proceeding with available tracts.")
print(f"  GeoDataFrame: {len(gdf)} features, {len(gdf.columns)} columns")

# ── Export ────────────────────────────────────────────────────────────────────
OUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
gdf.to_file(OUT_GEOJSON, driver="GeoJSON")
print(f"\nSaved -> {OUT_GEOJSON}")

SITE_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(OUT_GEOJSON, SITE_GEOJSON)
print(f"Copied -> {SITE_GEOJSON}")

# ── Report ────────────────────────────────────────────────────────────────────
print(f"\nColumns in GeoJSON ({len(gdf.columns)} total):")
for col in gdf.columns:
    null_n = gdf[col].isnull().sum()
    null_str = f"  ({null_n} nulls)" if null_n > 0 else ""
    print(f"  {col}{null_str}")

recommended_n = int(gdf["recommended"].sum()) if "recommended" in gdf.columns else "N/A"
print(f"\nRecommended tracts in output: {recommended_n}")
