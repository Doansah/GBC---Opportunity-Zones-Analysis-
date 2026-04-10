"""
05_geocode_to_tracts.py

Spatial-join Baltimore City parcel and permit records to census tract GEOIDs.

Uses the TIGER/Line 2025 Maryland census tract shapefile already on disk.
Both input CSVs must have X/Y (parcels) or latitude/longitude (permits) columns.

Inputs:
  data/raw/baltimore_real_property.csv
  data/raw/baltimore_building_permits.csv
  census_tract_shape_files/tl_2025_24_tract.shp

Outputs (overwrites inputs with geoid column added):
  data/raw/baltimore_real_property.csv
  data/raw/baltimore_building_permits.csv
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parent.parent
SHP_PATH = ROOT / "census_tract_shape_files" / "tl_2025_24_tract.shp"
PROPERTY_CSV = ROOT / "data" / "raw" / "baltimore_real_property.csv"
PERMITS_CSV = ROOT / "data" / "raw" / "baltimore_building_permits.csv"

BALT_CITY_PREFIX = "24510"


# ── 1. Load and prepare tract boundaries ─────────────────────────────────────
print("Loading census tract shapefile…")
tracts = gpd.read_file(SHP_PATH)
print(f"  Total MD tracts in shapefile: {len(tracts)}")

# Normalise GEOID column (TIGER files use 'GEOID')
geoid_col = next(c for c in tracts.columns if c.upper() == "GEOID")
tracts = tracts.rename(columns={geoid_col: "geoid"})
tracts["geoid"] = tracts["geoid"].str.strip().str.zfill(11)

# Filter to Baltimore City tracts only (county FIPS 510)
balt_tracts = tracts[tracts["geoid"].str.startswith(BALT_CITY_PREFIX)].copy()
print(f"  Baltimore City tracts: {len(balt_tracts)}")

# Reproject to WGS84 for joining against lat/lon points
balt_tracts = balt_tracts.to_crs("EPSG:4326")


def sjoin_to_tracts(df: pd.DataFrame, lon_col: str, lat_col: str, label: str) -> pd.DataFrame:
    """Point-in-polygon join of df rows to Baltimore City census tracts."""
    print(f"\nProcessing {label} ({len(df):,} rows)…")

    # Drop rows missing coordinates
    before = len(df)
    df = df.dropna(subset=[lon_col, lat_col]).copy()
    df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")
    df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
    df = df.dropna(subset=[lon_col, lat_col])
    print(f"  Rows with valid coordinates: {len(df):,} (dropped {before - len(df):,})")

    # Build GeoDataFrame
    geometry = [Point(x, y) for x, y in zip(df[lon_col], df[lat_col])]
    gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")

    # Spatial join
    joined = gpd.sjoin(
        gdf,
        balt_tracts[["geoid", "geometry"]],
        how="left",
        predicate="within",
    )

    # sjoin may create duplicate rows if a point falls on a boundary; keep first
    joined = joined[~joined.index.duplicated(keep="first")]

    matched = joined["geoid"].notna().sum()
    print(f"  Matched to a tract: {matched:,} ({matched/len(df)*100:.1f}%)")

    # Drop geometry and index_right before returning as plain DataFrame
    result = pd.DataFrame(joined.drop(columns=["geometry", "index_right"], errors="ignore"))
    return result


# ── 2. Parcels ────────────────────────────────────────────────────────────────
if PROPERTY_CSV.exists():
    prop_df = pd.read_csv(PROPERTY_CSV, dtype=str, low_memory=False)
    prop_df = sjoin_to_tracts(prop_df, lon_col="X", lat_col="Y", label="parcels")
    prop_df.to_csv(PROPERTY_CSV, index=False)
    print(f"  Saved enriched parcels -> {PROPERTY_CSV}")
else:
    print(f"WARNING: {PROPERTY_CSV} not found — skipping parcels")


# ── 3. Permits ────────────────────────────────────────────────────────────────
if PERMITS_CSV.exists():
    perm_df = pd.read_csv(PERMITS_CSV, dtype=str, low_memory=False)

    # Permits datasets use varying column names
    lon_col = next((c for c in perm_df.columns if c.lower() in ("longitude", "lon", "lng", "x")), None)
    lat_col = next((c for c in perm_df.columns if c.lower() in ("latitude", "lat", "y")), None)

    if lon_col and lat_col:
        perm_df = sjoin_to_tracts(perm_df, lon_col=lon_col, lat_col=lat_col, label="permits")
        perm_df.to_csv(PERMITS_CSV, index=False)
        print(f"  Saved enriched permits -> {PERMITS_CSV}")
    else:
        print(f"WARNING: No lat/lon columns found in permits CSV (cols: {list(perm_df.columns[:10])})")
        print("  Adding empty geoid column and continuing.")
        perm_df["geoid"] = pd.NA
        perm_df.to_csv(PERMITS_CSV, index=False)
else:
    print(f"WARNING: {PERMITS_CSV} not found — skipping permits")

print("\nDone — spatial join complete.")
