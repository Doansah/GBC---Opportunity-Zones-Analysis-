"""
12_export_geojson.py

Merges the scored tracts CSV with Maryland census tract geometries and
exports a GeoJSON file suitable for the static stakeholder voting site.

Input:
  data/output/scored_tracts.csv
  census_tract_shape_files/tl_2025_24_tract.shp

Output:
  data/scored_tracts.geojson   (target ≤3 MB after geometry simplification)
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).resolve().parent.parent
SCORED_CSV = ROOT / "data" / "output" / "scored_tracts.csv"
SHP_PATH   = ROOT / "census_tract_shape_files" / "tl_2025_24_tract.shp"
OUT_PATH   = ROOT / "data" / "scored_tracts.geojson"

# Properties to carry into each GeoJSON feature (all others are dropped)
KEEP_COLS = [
    "geoid", "state", "county",
    "classification", "oztoolclassification",
    "composite_score", "rank", "recommended",
    "jobs_2022", "povrate_2024", "median_hhincome_2024", "unemprate_2024",
    "vacancyrate_2024", "stackability_count", "pop_2024", "median_homevalue_2024",
    "job_density_score", "dev_capacity_score", "market_momentum_score",
    "poverty_score", "income_score", "unemployment_score", "stackability_score",
    "stage1_result",
]

# Simplification tolerance in degrees (~30 m at mid-latitudes).
# Reduces file size dramatically while remaining imperceptible at web zoom.
SIMPLIFY_TOLERANCE = 0.0003


def main() -> None:
    # ── Load scored CSV ───────────────────────────────────────────────────────
    print(f"Loading scored tracts from {SCORED_CSV} …")
    scored = pd.read_csv(SCORED_CSV, dtype={"geoid": str})
    scored["geoid"] = scored["geoid"].str.zfill(11)
    print(f"  {len(scored)} rows loaded")

    # ── Load shapefile ────────────────────────────────────────────────────────
    print(f"Loading shapefile from {SHP_PATH} …")
    tracts_shp = gpd.read_file(SHP_PATH)
    tracts_shp["GEOID"] = tracts_shp["GEOID"].str.zfill(11)
    print(f"  {len(tracts_shp)} tract polygons loaded, CRS={tracts_shp.crs}")

    # ── Merge ─────────────────────────────────────────────────────────────────
    gdf = tracts_shp.merge(scored, left_on="GEOID", right_on="geoid", how="inner")
    # Keep only the 451 eligible tracts (those that reached the scoring stage)
    gdf = gdf[gdf["stage1_result"].notna()].copy()
    print(f"  Merged: {len(gdf)} eligible tracts")

    # ── Select & clean columns ────────────────────────────────────────────────
    present = [c for c in KEEP_COLS if c in gdf.columns]
    missing = [c for c in KEEP_COLS if c not in gdf.columns]
    if missing:
        print(f"  Warning: columns not found and will be skipped: {missing}")
    gdf = gdf[present + ["geometry"]].copy()

    # Round floats for compact JSON output
    float_cols = gdf.select_dtypes(include="float").columns
    gdf[float_cols] = gdf[float_cols].round(6)

    # Cast rank to nullable int so it serialises as an integer (not 1.0)
    if "rank" in gdf.columns:
        gdf["rank"] = gdf["rank"].astype("Int64")

    # ── Reproject to WGS-84 (required for GeoJSON) ───────────────────────────
    gdf = gdf.to_crs("EPSG:4326")

    # ── Simplify geometry ─────────────────────────────────────────────────────
    print(f"  Simplifying geometry (tolerance={SIMPLIFY_TOLERANCE}°) …")
    gdf["geometry"] = gdf["geometry"].simplify(
        SIMPLIFY_TOLERANCE, preserve_topology=True
    )

    # ── Export ────────────────────────────────────────────────────────────────
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(OUT_PATH, driver="GeoJSON")
    size_mb = OUT_PATH.stat().st_size / 1_048_576
    print(f"\nExported {len(gdf)} features → {OUT_PATH}")
    print(f"  File size: {size_mb:.2f} MB")

    # Quick sanity check
    classifications = gdf["classification"].value_counts().to_dict()
    print(f"  Classification breakdown: {classifications}")
    print(f"  Recommended: {int(gdf['recommended'].sum())} tracts")


if __name__ == "__main__":
    main()
