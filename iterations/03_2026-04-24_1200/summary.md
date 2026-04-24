# Iteration 03 — 2026-04-24

## Session Goal
Add a `neighborhood` field to all 451 Maryland census tracts and display it on map hover tooltips.

## What Was Built or Changed

### New script: `scripts/12_add_neighborhoods.py`
Adds a `neighborhood` column to `scored_tracts.csv` and patches `docs/data/scored_tracts.geojson` in-place.

**Two-source strategy:**
- **Baltimore City tracts (24510 prefix):** Mode of the `neighborhood` column from `data/raw/baltimore_building_permits.csv` — already geocoded to tracts in iteration 01, already has neighborhood names attached.
- **All other MD tracts:** Census TIGER 2020 Places shapefile (via `zip+https://www2.census.gov/geo/tiger/TIGER2020/PLACE/tl_2020_24_place.zip`). Point-in-polygon join using tract centroid (projected to UTM 18N for accuracy, then back to WGS84 for the join).
- **Fallback:** county name for tracts outside any named place (50 tracts, mostly rural).

### Tooltip update: `docs/app.js`
- Title line now shows `{geoid} — {neighborhood}` instead of `{geoid} — {county}`
- New subtitle line shows county name (in grey) when a specific neighborhood is available

### Style update: `docs/style.css`
- Added `.tt-subtitle` rule: small grey text below the tooltip title

## Data Sources & Actual Endpoints Used
- **Permits data:** `data/raw/baltimore_building_permits.csv` — already had `neighborhood` + `geoid` columns from prior pipeline
- **TIGER Places:** `https://www2.census.gov/geo/tiger/TIGER2020/PLACE/tl_2020_24_place.zip` — geopandas reads this zip URL directly
- **Attempted but failed:** Open Baltimore ArcGIS services1.arcgis.com NSA endpoint (400 error); egisdata.baltimorecity.gov BNIAJFI MapServer (returned empty fields). Permits data made these unnecessary for Baltimore City.

## Results / Outputs
| Coverage | Count |
|---|---|
| Total tracts | 451 |
| Baltimore City tracts with specific neighborhood | ~130 of 138 |
| Other MD tracts matched to Census place | ~271 of 313 |
| Fallback to county name | 50 |

Sample output:
- `24510160600` [Baltimore city] → **Mosher**
- `24510271802` [Baltimore city] → **Central Park Heights**
- `24005451500` [Baltimore County] → **Middle River**
- `24005452300` [Baltimore County] → **Dundalk**
- `24033802804` [Prince George's County] → **Walker Mill**
- `24033801216` [Prince George's County] → **Clinton**

**Files modified:**
- `docs/data/scored_tracts.geojson` — neighborhood property added to all 451 features (in-place patch, preserves exact GeoJSON structure)
- `data/output/scored_tracts_new.csv` — updated CSV with neighborhood column (original locked by another process; rename when Excel is closed)
- `docs/app.js` — tooltip title + county subtitle
- `docs/style.css` — .tt-subtitle style

## Key Technical Findings / Gotchas
- **Permits data already had what we needed:** The `neighborhood` + `geoid` columns were both present in `data/raw/baltimore_building_permits.csv` from the iteration 01 pipeline. No new API calls needed for Baltimore City.
- **GeoJSON patching approach:** Rather than letting geopandas rewrite the entire GeoJSON (which can subtly change number precision and structure), the script loads the JSON, adds one property per feature, and writes back. This is safer.
- **Centroid projection:** geopandas warns if you compute centroids in EPSG:4326 (lon/lat). Must reproject to EPSG:32618 (UTM 18N) first, then bring centroids back to WGS84 for the spatial join.
- **GeoDataFrame centroid assignment:** In newer geopandas/pandas, you cannot assign to `gdf.geometry` via attribute access — must use `gpd.GeoDataFrame(data, geometry=..., crs=...)` constructor.
- **CSV locked by OneDrive/Excel:** The original `scored_tracts.csv` was locked. Updated version saved as `scored_tracts_new.csv` — rename when original is free.
