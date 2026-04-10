# Iteration 01 — Session Summary

**Date:** 2026-04-10  
**Time:** 16:34  
**Session goal:** Build the full OZ data pipeline from scratch — data acquisition through weighted scoring.

---

## What Was Built

### Project Scaffold
- Created directory structure: `data/raw/`, `data/processed/`, `data/output/`, `scripts/`, `notebooks/`, `iterations/`
- Created `requirements.txt` with core dependencies: `pandas`, `geopandas`, `requests`, `shapely`, `pyproj`

### Scripts Written (10 total)

| Script | Purpose |
|--------|---------|
| `01_pull_urban_institute.py` | Filter national UI CSV to Maryland's 451 eligible tracts; add short classification labels |
| `02_pull_baltimore_property.py` | Pull 237k Baltimore parcel records from ArcGIS (dmxOwnership MapServer) |
| `03_pull_baltimore_permits.py` | Pull 278k Baltimore building permits from ArcGIS (DHCD MapServer) |
| `04_pull_incentive_zones.py` | Pull Enterprise Zones, Sustainable Communities, RISE Zones from MD iMAP |
| `05_geocode_to_tracts.py` | Point-in-polygon spatial join of parcels/permits to census tract GEOIDs |
| `06_aggregate_property_stats.py` | Derive tract-level property metrics (vacancy, land/value ratio, market activity) |
| `07_aggregate_permit_stats.py` | Derive tract-level permit metrics (volume, trend, new construction share) |
| `08_build_master_table.py` | Join all sources into single 451-row master table; compute stackability scores |
| `09_apply_filters.py` | Stage 1 hard filters (unviable / already attractive) |
| `10_score_tracts.py` | Stage 2 weighted composite scoring; rank and flag top 113 recommendations |

---

## Data Sources & Actual Endpoints Used

| Source | Endpoint Used | Notes |
|--------|--------------|-------|
| Urban Institute OZ Tool | Local CSV (`UrbanInstitute_OZDesignationTool_3_9_2026_0.csv`) | Already on disk |
| Baltimore Real Property | `egisdata.baltimorecity.gov/.../dmxOwnership/MapServer/0` | **Not** FeatureServer — that returns 500. Field names differ from CLAUDE.md docs (FULLCASH not CURRVAL, DHCDUSE1 not DESCLU, VACIND not VACESSION, OWNMDE not OWNER_OCCUP) |
| Baltimore Building Permits | `egisdata.baltimorecity.gov/.../DHCD_Open_Baltimore_Datasets/MapServer/3` | Socrata API at data.baltimorecity.gov no longer works — site moved to ArcGIS Hub |
| MD iMAP Incentive Zones | `mdgeodata.md.gov/imap/rest/services/BusinessEconomy/MD_IncentiveZones/MapServer` | geodata.md.gov redirects to deprecation page; use mdgeodata.md.gov |
| Census Tract Boundaries | `census_tract_shape_files/tl_2025_24_tract.shp` | Already on disk (2025 TIGER/Line, 1,475 MD tracts) |

---

## Pipeline Results

### Data Volumes
- **237,131** Baltimore parcels pulled and spatially joined (99.9% match rate)
- **278,264** Baltimore permits pulled and spatially joined (100% match rate)
- **32** Enterprise Zone polygons, **123** Sustainable Community polygons, **3** RISE Zone polygons

### Stage 1 Filters
| Result | Count |
|--------|-------|
| Eliminated — Already Attractive | 92 |
| Eliminated — Unviable | 0 |
| Advances to Scoring | 359 |

Thresholds used:
- Metro median income: $65,485
- Top quartile home value: $361,900

Note: Zero tracts eliminated as unviable because no tract had extreme poverty (>45%) + low jobs (<200) + zero permits simultaneously.

### Stackability Distribution
| Overlapping incentive zones | Tracts |
|-----------------------------|--------|
| 0 | 160 |
| 1 | 260 |
| 2 | 31 |
| 3 | 0 |

### Scoring Weights Applied
| Dimension | Sub-score | Weight |
|-----------|-----------|--------|
| Investment Viability | Job density | 30% |
| Investment Viability | Development capacity | 12% |
| Investment Viability | Market momentum | 10% |
| Community Need | Poverty score | 15% |
| Community Need | Income score | 10% |
| Community Need | Unemployment score | 8% |
| Stackability | Incentive zone overlap | 15% |

### Top 5 Recommended Tracts
| GEOID | County | Classification | Score | Jobs | Poverty |
|-------|--------|----------------|-------|------|---------|
| 24510040200 | Baltimore City | Already Attractive | 0.715 | 21,188 | 30.6% |
| 24510070400 | Baltimore City | Already Attractive | 0.596 | 10,579 | 33.4% |
| 24510060400 | Baltimore City | Goldilocks | 0.546 | 14,007 | 27.1% |
| 24510260605 | Baltimore City | Already Attractive | 0.528 | 15,855 | 14.6% |
| 24005490900 | Baltimore County | Goldilocks | 0.486 | 11,669 | 22.9% |

### Final Recommendation Pool (113 tracts)
| Classification | Count |
|----------------|-------|
| Less Likely | 71 |
| Already Attractive | 23 |
| Goldilocks | 19 |

---

## Key Technical Findings / Gotchas

1. **API endpoint changes:** The CLAUDE.md docs reference `geodata.md.gov` (now deprecated) and `data.baltimorecity.gov` Socrata (no longer JSON). Both corrected.
2. **FeatureServer vs MapServer:** `dmxOwnership` FeatureServer returns HTTP 500. Must use MapServer.
3. **Polygon geometry:** Both parcel and permit layers return polygon footprints, not points. Centroids extracted by averaging ring vertices.
4. **Unix ms timestamps:** ArcGIS `IssuedDate` and `SALEDATE_good` fields are Unix millisecond timestamps. Use `pd.to_datetime(col, unit='ms')`.
5. **`infer_datetime_format` removed:** Dropped in recent pandas. Use bare `pd.to_datetime()`.
6. **geopandas CRS warning:** Computing centroids in geographic CRS (EPSG:4326) generates a warning but is acceptable precision for tract-level intersection checks.

---

## Output Files
- `data/processed/md_tracts_base.csv` — 451 MD tracts with Urban Institute classifications
- `data/processed/baltimore_tract_property_stats.csv` — property metrics for 199 Baltimore tracts
- `data/processed/baltimore_tract_permit_stats.csv` — permit metrics for 199 Baltimore tracts
- `data/processed/md_tracts_master.csv` — full 451-row joined table (41 columns)
- `data/processed/md_tracts_filtered.csv` — master table with Stage 1 filter labels
- `data/output/scored_tracts.csv` — final scored and ranked output
