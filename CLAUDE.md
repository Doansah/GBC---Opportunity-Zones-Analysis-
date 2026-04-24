# Opportunity Zones Data Pipeline — Project Context

## What This Project Is

We are building a data analysis pipeline to evaluate Maryland's 451 eligible census tracts for Opportunity Zone (OZ) 2.0 designation. The goal is to identify "Goldilocks tracts" — tracts that are distressed enough to genuinely need investment but have enough economic infrastructure to actually attract private capital. The output will be presented to Maryland state government and development stakeholders (Greater Baltimore Committee).

The governor can designate up to 25% of eligible tracts (~113) as Opportunity Zones. Our job is to recommend which tracts to designate, backed by data.

## The Analytical Framework

We score tracts on two dimensions simultaneously:

**Investment Viability (~50-55% of evaluation):** Will private capital actually flow here? The strongest predictor from Ohio research is job density (58% gap between Goldilocks and non-Goldilocks tracts). Secondary signals: development capacity (vacancy, land utilization), market momentum (permit activity, sale prices), and incentive stackability (overlap with other tax incentive zones).

**Community Need (~30-35% of evaluation):** Does the tract genuinely need the investment? Measured by poverty rate, median income, unemployment, educational attainment. Key insight: moderate distress (20-35% poverty) with some economic base attracts investment; extreme distress (45%+ poverty) with no economic infrastructure does not.

**Incentive Stackability (~15-20%):** Does the tract overlap with Enterprise Zones, Sustainable Communities, Qualified Census Tracts (LIHTC), NMTC-eligible areas? More overlaps = stronger candidate because developers can layer multiple funding sources.

## The Three-Stage Evaluation

**Stage 1 — Hard Filters:** Eliminate clearly unviable tracts and clearly redundant tracts.
- Filter OUT: "Less Likely" tracts with <200 jobs AND >45% poverty AND zero permit activity (designation will go unused)
- Filter OUT: "Already Attractive" tracts where income exceeds metro median AND home values are in the top quartile (designation is redundant — capital flows regardless)
- Everything else advances to scoring.

**Stage 2 — Weighted Scoring:** Composite score for surviving tracts across investment viability, community need, and stackability dimensions.

**Stage 3 — Tract Profiles:** Top 20-30 tracts get individual narrative profiles with development opportunity descriptions. (Not part of the data pipeline — this is qualitative analysis done later.)

---

## Data Sources and File Descriptions

### 1. Urban Institute OZ Designation Tool (ALREADY HAVE)

**File:** `UrbanInstitute_OZDesignationTool_3_9_2026_0.csv`
**Scope:** 25,259 census tracts nationally; 451 in Maryland
**Role:** Pre-built classification layer and national benchmark. This is the backbone.

**Columns:**
```
geoid                       - 11-digit census tract FIPS code (string, e.g., "24510060400")
                              Format: SS_CCC_TTTTTT (state + county + tract)
                              Maryland state FIPS = 24
                              Baltimore City county FIPS = 510
                              Prince George's County = 033
                              Baltimore County = 005
state                       - State name
county                      - County name
oztoolclassification        - One of three values:
                              "Less likely to attract OZ investment"
                              "More likely to attract OZ investment, with larger impact"  [= GOLDILOCKS]
                              "Likely to attract capital even without OZ designation"
likelyrural                 - Binary (0/1)
pop_2024                    - Population
median_hhincome_2024        - Median household income (dollars)
povrate_2024                - Poverty rate (decimal, e.g., 0.21)
unemprate_2024              - Unemployment rate (decimal)
jobs_2022                   - Job count in tract (integer) — THIS IS THE #1 PREDICTOR
median_homevalue_2024       - Median home value (dollars)
median_grossrent_2024       - Median gross rent (dollars)
pct_own_2024                - Homeownership rate (decimal)
pct_severerentburden_2024   - Severe rent burden rate (decimal)
vacancyrate_2024            - Vacancy rate (decimal)
pct_age1824_2024            - % age 18-24 (decimal)
pct_white_2024              - % white (decimal)
pct_black_2024              - % Black (decimal)
pct_latino_2024             - % Latino (decimal)
pct_aapi_2024               - % AAPI (decimal)
pct_ba_2024                 - % with bachelor's degree (decimal)
cbsa_type                   - "Metro", "Micro", or "Outside CBSA"
```

**Key Maryland stats from our analysis:**
- 451 total eligible tracts
- 66 Goldilocks tracts (14.6%)
- 64 Already Attractive (14.2%)
- 321 Less Likely (71.2%)
- Goldilocks concentrated in: Baltimore City (28), Prince George's County (18), Baltimore County (7)

**To filter Maryland rows:**
```python
df = pd.read_csv("UrbanInstitute_OZDesignationTool_3_9_2026_0.csv")
md = df[df['state'] == 'Maryland'].copy()
```

---

### 2. Open Baltimore — Real Property Assessments (SDAT) (NEED TO PULL)

**API Endpoint:** `https://data.baltimorecity.gov/datasets/baltimore::real-property-information-2/api`
**ArcGIS Feature Service:** `https://egisdata.baltimorecity.gov/egis/rest/services/Housing/dmxOwnership/FeatureServer/0`
**Scope:** All parcels in Baltimore City (~230,000 parcels). Covers 138 of Maryland's 451 eligible tracts.
**Role:** Parcel-level development capacity analysis. Ground-truth layer for Baltimore City.

**Key fields we need (from SDAT data dictionary):**
```
BLOCKLOT or BLOCK_LOT   - Parcel identifier
WARD                    - Ward number
SECTION                 - Section number  
FULLADDR                - Full street address
ZIPCODE                 - ZIP code
NEIGHBOR                - Neighborhood name
CURRLAND                - Current assessed land value (dollars)
CURRIMPR                - Current assessed improvement value (dollars)
CURRVAL                 - Current total assessed value (CURRLAND + CURRIMPR)
SALEPRIC                - Most recent sale price
SALEDATE                - Most recent sale date
PREVLAND                - Previous assessed land value
PREVIMPR                - Previous assessed improvement value
DESCLU                  - Description of land use (e.g., "RESIDENTIAL", "COMMERCIAL", "EXEMPT", "INDUSTRIAL")
USEGROUP                - Use group code
PERMESSION              - Use permission
VACESSION               - Vacant indicator or session
OWNER_1                 - Owner name
OWNER_OCCUP             - Owner occupied (Y/N)
GROUNDRENT              - Ground rent amount
```

**The tract linkage problem:**
Open Baltimore parcel data does NOT have a census tract field. You will need to either:
1. Geocode parcels and spatially join to census tract boundaries, OR
2. Use a crosswalk file (block/lot to tract), OR
3. Use the latitude/longitude if available in the dataset and do a point-in-polygon join

The census tract boundary shapefile for Baltimore City (2020 tracts) is available from:
- Open Baltimore: `https://data.baltimorecity.gov/datasets/census-tracts-2020`
- TIGER/Line: `https://www.census.gov/cgi-bin/geo/shapefiles/index.php` (select Maryland, Census Tracts)

**What we derive from this data (aggregated to census tract level):**
```
land_to_value_ratio     = mean(CURRLAND / CURRVAL) per tract
                          High ratio = land is valuable but buildings are not = development opportunity

vacancy_proxy           = count of parcels where DESCLU contains "VACANT" or improvement value = 0
                          per tract / total parcels per tract

market_activity         = count of sales in last 3 years per tract
                          + median sale price per tract
                          + trend in sale prices (compare recent vs older sales)

owner_occupancy_rate    = count(OWNER_OCCUP == 'Y') / total residential parcels per tract
                          Low owner-occupancy = less displacement risk from new development
                          High owner-occupancy = community stability concern

property_use_mix        = share of parcels by DESCLU category per tract
                          Tracts with commercial/industrial mix = more job-proximate
                          Tracts that are 100% residential = bedroom communities

assessed_value_per_sqft = if square footage available, normalize values for comparison
```

---

### 3. Housing & Building Permits — Baltimore City (NEED TO PULL)

**Source:** Baltimore Housing's Office of Permits & Building Inspections, via Open Baltimore
**API:** Search Open Baltimore for "housing permits" or "building permits"
**Historical data (2015-2018):** `https://data.baltimorecity.gov` — search for housing permits dataset
**Scope:** Baltimore City only. Permits issued for construction, renovation, demolition.

**Key fields we need:**
```
permit_number           - Unique ID
permit_type             - Type (new construction, renovation, demolition, etc.)
use_code or description - Residential, commercial, mixed-use
issue_date              - When permit was issued
location / address      - For geocoding to tract
latitude / longitude    - If available, for spatial join to tract
```

**What we derive (aggregated to census tract level):**
```
permits_total           = count of all permits per tract (last 5 years)
permits_new_construction = count of new construction permits per tract
permits_residential     = count of residential permits
permits_commercial      = count of commercial permits
permit_trend            = permits in recent 2 years vs prior 3 years (growing/shrinking)
has_any_permits         = binary flag (tracts with zero = red flag for investment viability)
```

---

### 4. ACS 5-Year Estimates 2020-2024 (SUPPLEMENTARY — Urban Institute already captures most of this)

The Urban Institute tool already includes the core ACS variables (income, poverty, unemployment, etc.) for all 451 Maryland tracts. We may want the **comparison profiles** (2020-2024 vs 2015-2019) for trend analysis, but this is a secondary priority.

**If needed, the Census API call for Maryland tracts would look like:**
```
https://api.census.gov/data/2024/acs/acs5/profile?get=DP03_0062E,DP03_0009PE,DP03_0119PE&for=tract:*&in=state:24&key=YOUR_KEY
```

Where:
- `DP03_0062E` = Median household income
- `DP03_0009PE` = Unemployment rate  
- `DP03_0119PE` = Poverty rate
- `state:24` = Maryland
- `tract:*` = All tracts

---

### 5. MD iMAP Incentive Zones (SUPPLEMENTARY — for stackability scoring)

**REST API Base:** `https://geodata.md.gov/imap/rest/services/BusinessEconomy/MD_IncentiveZones/MapServer`

**Layers available:**
```
0  - Maple Streets Areas
1  - Main Streets Areas
2  - Arts and Entertainment Districts
3  - BRAC Zones
4  - Enterprise Zones
5  - Enterprise Zone Focus Areas
6  - Sustainable Communities
7  - One Maryland Jurisdictions
8  - Empowerment Zones
9  - Foreign Trade Zones
10 - Heritage Areas
11 - RISE Zones
```

**Most relevant for OZ stackability:** Layers 4 (Enterprise Zones), 6 (Sustainable Communities), 11 (RISE Zones)

**Query example to get Enterprise Zone polygons:**
```
https://geodata.md.gov/imap/rest/services/BusinessEconomy/MD_IncentiveZones/MapServer/4/query?where=1%3D1&outFields=*&f=geojson
```

**What we derive:** For each census tract, count how many incentive zones overlap it. More overlaps = higher stackability score.

---

## Project File Structure

```
oz-data-pipeline/
├── CLAUDE.md                    # This file — project context
├── data/
│   ├── raw/
│   │   ├── urban_institute_oz_tool.csv        # Already have this
│   │   ├── baltimore_real_property.csv         # Pull from Open Baltimore API
│   │   ├── baltimore_building_permits.csv      # Pull from Open Baltimore
│   │   ├── census_tracts_2020_md.geojson       # Tract boundaries for spatial joins
│   │   └── imap_incentive_zones/               # GeoJSON from MD iMAP layers
│   │       ├── enterprise_zones.geojson
│   │       ├── sustainable_communities.geojson
│   │       └── rise_zones.geojson
│   ├── processed/
│   │   ├── md_tracts_master.csv                # All 451 MD tracts with all derived variables
│   │   ├── baltimore_tract_property_stats.csv  # SDAT aggregated to tract level
│   │   └── baltimore_tract_permit_stats.csv    # Permits aggregated to tract level
│   └── output/
│       ├── scored_tracts.csv                   # Final scored and ranked tracts
│       └── tract_profiles/                     # Individual tract profile summaries
├── scripts/
│   ├── 01_pull_urban_institute.py              # Filter UI data to Maryland
│   ├── 02_pull_baltimore_property.py           # Pull SDAT from Open Baltimore API
│   ├── 03_pull_baltimore_permits.py            # Pull permit data from Open Baltimore
│   ├── 04_pull_incentive_zones.py              # Pull iMAP GeoJSON layers
│   ├── 05_geocode_to_tracts.py                 # Spatial join parcels/permits to tracts
│   ├── 06_aggregate_property_stats.py          # Derive tract-level property metrics
│   ├── 07_aggregate_permit_stats.py            # Derive tract-level permit metrics
│   ├── 08_build_master_table.py                # Join all data into one tract-level table
│   ├── 09_apply_filters.py                     # Stage 1 hard filters
│   └── 10_score_tracts.py                      # Stage 2 weighted scoring
├── notebooks/                                  # Exploratory analysis
│   └── eda.ipynb
└── requirements.txt
```

## Dependencies

```
pandas
geopandas
requests
shapely
pyproj
```

## What to Build First

**Priority 1:** `01_pull_urban_institute.py` — Filter the Urban Institute CSV to Maryland's 451 tracts. Add short classification labels ("Goldilocks", "Less Likely", "Already Attractive"). Save as `md_tracts_base.csv`. This is the backbone everything joins to.

**Priority 2:** `02_pull_baltimore_property.py` — Pull Real Property data from Open Baltimore's ArcGIS API. The feature service uses pagination (max 2000 records per request). Save raw data, then aggregate to tract level in a separate script.

**Priority 3:** `03_pull_baltimore_permits.py` — Pull building permit data from Open Baltimore. Same pagination approach.

**Priority 4:** `05_geocode_to_tracts.py` + `06_aggregate_property_stats.py` — Spatial join parcels to census tracts (requires tract boundary shapefile), then compute tract-level derived variables (land_to_value_ratio, vacancy_proxy, market_activity, etc.)

**Priority 5:** `08_build_master_table.py` — Join everything into one row-per-tract master table with columns from Urban Institute + SDAT-derived + permit-derived variables.

**Priority 6:** `09_apply_filters.py` and `10_score_tracts.py` — Apply the evaluation framework.

## Key Technical Notes

- **Census tract GEOID format:** 11 digits, string not integer. Maryland = "24", Baltimore City = "24510", Prince George's = "24033". Always preserve leading zeros.
- **Open Baltimore ArcGIS pagination:** Feature services cap at 1000-2000 records per request. Use `resultOffset` and `resultRecordCount` parameters to paginate.
- **Spatial joins:** Parcel data likely needs point-in-polygon join to tract boundaries. If parcel data has lat/lon, use geopandas. If not, geocode from address or use the BLOCKLOT-to-tract crosswalk if one exists.
- **Data type consistency:** Poverty rates, unemployment, etc. in the Urban Institute file are decimals (0.21 = 21%). Maintain this format throughout.
- **Missing data:** Some Urban Institute fields have blanks (e.g., median_grossrent for tracts with very few renters). Handle gracefully — don't drop rows, flag missingness.

---

## Iteration Logging — Required After Every Session

At the end of every working session, create an iteration summary:

1. Create a folder: `iterations/NN_YYYY-MM-DD_HHMM/` (e.g. `iterations/02_2026-04-15_1045/`)
   - `NN` = zero-padded iteration number (01, 02, 03 …)
   - Use the actual local time when the session ends
2. Create `iterations/NN_.../summary.md` containing:
   - **Date / Time**
   - **Session goal** — what was being worked on
   - **What was built or changed** — scripts added/modified, data pulled, bugs fixed
   - **Data sources & actual endpoints used** — update if any URLs or field names changed from the docs
   - **Results / outputs** — row counts, key numbers, output file names
   - **Key technical findings / gotchas** — anything that differed from the plan or will matter next session

This is mandatory — do not end a session without creating the iteration folder and summary.

### Iteration Log
| # | Folder | Summary |
|---|--------|---------|
| 01 | `iterations/01_2026-04-10_1634/` | Full pipeline built and executed end-to-end: 10 scripts, 237k parcels + 278k permits pulled, 451 MD tracts scored, 113 recommended designations produced |
| 02 | `iterations/02_2026-04-22_1200/` | Scoring V2: rebuilt scoring around 8 zero-null ACS inputs; removed Baltimore-only and stackability from score; fixed unviable filter; added null guard; created GeoJSON export (script 11); updated site tooltip and methodology page |
| 03 | `iterations/03_2026-04-24_1200/` | Added neighborhood field to all 451 tracts (script 12): Baltimore City from permits data, rest from Census TIGER Places; patched GeoJSON; updated tooltip to show neighborhood name + county subtitle |
