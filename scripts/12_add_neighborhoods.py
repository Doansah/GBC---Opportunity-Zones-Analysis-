#!/usr/bin/env python3
"""
Add neighborhood/place names to scored_tracts.csv and scored_tracts.geojson.

Baltimore City tracts (geoid prefix 24510)
  -> mode of 'neighborhood' field in raw building permits (already geocoded to tracts)
All other MD tracts
  -> Census TIGER 2020 Places (cities, towns, CDPs)
Unmatched tracts (rural, outside any named place)
  -> county name
"""

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT        = Path(__file__).parent.parent
GEOJSON_IN  = ROOT / 'docs/data/scored_tracts.geojson'
CSV_IN      = ROOT / 'data/output/scored_tracts.csv'
CSV_OUT     = ROOT / 'data/output/scored_tracts.csv'
GEOJSON_OUT = ROOT / 'docs/data/scored_tracts.geojson'

PERMITS_RAW = ROOT / 'data/raw/baltimore_building_permits.csv'

# Census TIGER 2020 Maryland Places — geopandas reads zip URLs directly
MD_PLACES_ZIP = 'zip+https://www2.census.gov/geo/tiger/TIGER2020/PLACE/tl_2020_24_place.zip'


# ── Step 1: Baltimore City neighborhoods from permits ──────────────────────

def balt_neighborhoods_from_permits() -> dict:
    """
    Return {geoid -> neighborhood_name} for Baltimore City tracts.
    Uses the modal neighborhood from the raw building permits CSV,
    which already has both geoid and neighborhood columns from prior pipeline runs.
    """
    print('[1/3] Baltimore City neighborhoods from permits data...')
    df = pd.read_csv(PERMITS_RAW, dtype={'geoid': str},
                     usecols=['geoid', 'neighborhood'])

    balt = df[df['geoid'].str.startswith('24510', na=False)].copy()
    balt = balt[balt['neighborhood'].notna() & (balt['neighborhood'].str.strip() != '')]

    def _mode(s):
        m = s.mode()
        return m.iloc[0] if len(m) else ''

    lookup = balt.groupby('geoid')['neighborhood'].agg(_mode).to_dict()
    print(f'  Covered {len(lookup)} Baltimore City tracts')
    return lookup


# ── Step 2: Census TIGER Places for remaining tracts ──────────────────────

def tiger_places_gdf() -> gpd.GeoDataFrame | None:
    """Download Maryland TIGER 2020 Places and return a GeoDataFrame."""
    print('[2/3] Downloading Census TIGER 2020 Places for Maryland...')
    try:
        gdf = gpd.read_file(MD_PLACES_ZIP)
        gdf = gdf[['NAME', 'geometry']].copy().to_crs('EPSG:4326')
        print(f'  Got {len(gdf)} Maryland places')
        return gdf
    except Exception as exc:
        print(f'  TIGER download failed: {exc}')
        return None


def places_lookup(tracts_gdf: gpd.GeoDataFrame,
                  places: gpd.GeoDataFrame) -> dict:
    """
    Spatial join tract centroids to TIGER place polygons.
    Returns {geoid -> place_name}.
    """
    # Compute centroids in a projected CRS (UTM 18N) for accuracy,
    # then return to WGS84 for the spatial join.
    centroid_geom = tracts_gdf.to_crs('EPSG:32618').geometry.centroid.to_crs('EPSG:4326')
    centroids = gpd.GeoDataFrame(
        {'geoid': tracts_gdf['geoid'].values},
        geometry=centroid_geom.values,
        crs='EPSG:4326',
    )

    joined = gpd.sjoin(
        centroids,
        places[['NAME', 'geometry']],
        how='left',
        predicate='within',
    ).drop_duplicates(subset='geoid', keep='first')

    result = (
        joined[joined['NAME'].notna()]
        .set_index('geoid')['NAME']
        .to_dict()
    )
    print(f'  Matched {len(result)} tracts to a Census place')
    return result


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print('Loading scored_tracts GeoJSON...')
    gdf = gpd.read_file(str(GEOJSON_IN))
    print(f'  {len(gdf)} features\n')

    # ── 1. Baltimore City from permits ─────────────────────────────────────
    balt_map = balt_neighborhoods_from_permits()

    # ── 2. TIGER Places for non-Baltimore tracts ───────────────────────────
    non_balt_gdf = gdf[~gdf['geoid'].astype(str).str.startswith('24510')].copy()
    print()
    places = tiger_places_gdf()
    tiger_map = places_lookup(non_balt_gdf, places) if places is not None else {}
    print()

    # ── 3. Build neighborhood series ──────────────────────────────────────
    print('[3/3] Assembling neighborhood column...')
    neighborhoods = []
    fallback_count = 0

    for _, row in gdf.iterrows():
        geoid  = str(row['geoid'])
        county = str(row['county'])

        if geoid.startswith('24510'):
            nbhd = balt_map.get(geoid, '')
        else:
            nbhd = tiger_map.get(geoid, '')

        if not nbhd:
            nbhd = county
            fallback_count += 1

        neighborhoods.append(nbhd)

    gdf['neighborhood'] = neighborhoods
    print(f'  Fallback to county name: {fallback_count} tracts')

    # ── Diagnostics ────────────────────────────────────────────────────────
    print('\n-- Sample output (first 25 tracts) --')
    for _, row in gdf[['geoid', 'county', 'neighborhood']].head(25).iterrows():
        print(f'  {row["geoid"]}  [{row["county"]}]  ->  {row["neighborhood"]}')

    balt_matched = sum(1 for g, n in zip(gdf['geoid'], gdf['neighborhood'])
                       if str(g).startswith('24510') and n != gdf.loc[gdf['geoid'] == g, 'county'].values[0])
    print(f'\nCoverage:')
    print(f'  Total tracts: {len(gdf)}')
    print(f'  Baltimore City: {(gdf["geoid"].astype(str).str.startswith("24510")).sum()} tracts')
    print(f'  Matched to named neighborhood/place: {len(gdf) - fallback_count}')
    print(f'  Fallback (county name): {fallback_count}')

    # ── Patch GeoJSON in-place (preserves exact structure) ─────────────────
    print(f'\nPatching {GEOJSON_OUT}...')
    with open(GEOJSON_IN, 'r', encoding='utf-8') as f:
        geojson_data = json.load(f)

    nbhd_lookup = dict(zip(gdf['geoid'].astype(str), gdf['neighborhood']))
    for feature in geojson_data['features']:
        geoid = str(feature['properties'].get('geoid', ''))
        feature['properties']['neighborhood'] = nbhd_lookup.get(geoid, '')

    with open(GEOJSON_OUT, 'w', encoding='utf-8') as f:
        json.dump(geojson_data, f, separators=(',', ':'))
    print('  GeoJSON written')

    # ── Update CSV ─────────────────────────────────────────────────────────
    print(f'Updating {CSV_OUT}...')
    df = pd.read_csv(CSV_IN, dtype={'geoid': str})
    if 'neighborhood' in df.columns:
        df = df.drop(columns=['neighborhood'])

    nbhd_df = pd.DataFrame({
        'geoid':        gdf['geoid'].astype(str).values,
        'neighborhood': gdf['neighborhood'].values,
    })
    df = df.merge(nbhd_df, on='geoid', how='left')
    df.to_csv(CSV_OUT, index=False)
    print('  CSV written')

    print('\nDone.')


if __name__ == '__main__':
    main()
