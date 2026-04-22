# Iteration 02 — Scoring V2

## Date / Time
2026-04-22

## Session Goal
Rebuild the scoring methodology so every input is available for all 451 tracts with zero nulls. Baltimore-specific parcel/permit data moves to supplementary display only. Fix the unviable filter that was silently misfiring on non-Baltimore tracts. Remove stackability from composite score. Create GeoJSON export for the interactive site.

---

## What Was Built or Changed

### `scripts/09_apply_filters.py` — Modified
- **Tiered unviable filter**: Baltimore City tracts (geoid starts "24510") still require all three conditions (`jobs < 200 AND pov > 0.45 AND has_any_permits == 0`). Non-Baltimore tracts now use two conditions only (`jobs < 200 AND pov > 0.45`) — permit data doesn't exist for them so the old third condition was always trivially true.
- **Goldilocks warning check**: After assigning stage1 results, the script now prints a warning if any Goldilocks-classified tracts are eliminated by the "Already Attractive" filter. **Finding: 17 Goldilocks tracts are being caught — needs investigation.**

### `scripts/10_score_tracts.py` — Rewritten
- **Removed from scoring**: `dev_capacity_score` (used `land_to_value_ratio` + `vacancy_proxy`), `market_momentum_score` (used `permit_trend` + `median_sale_price`), `stackability_score` (used `stackability_count`)
- **Added to scoring**: `vacancy_rate_score`, `home_value_inv_score`, `ownership_inv_score`, `education_inv_score`, renamed `income_score` → `income_inv_score`
- **New weights** (sum exactly 1.0):
  - `job_density_score` 0.30, `vacancy_rate_score` 0.10, `home_value_inv_score` 0.10, `ownership_inv_score` 0.05
  - `poverty_score` 0.18, `income_inv_score` 0.12, `unemployment_score` 0.08, `education_inv_score` 0.07
- **Null guard**: Checks all 8 inputs before scoring. Six are guaranteed non-null. Two (`median_homevalue_2024`, `median_hhincome_2024`) have ACS data gaps — imputed explicitly with advancing-tract median, with full logging of affected tracts (not silent).

### `scripts/11_export_geojson.py` — Created (new file)
- Merges `scored_tracts.csv` with `tl_2025_24_tract.shp`
- Exports to `data/output/scored_tracts.geojson` and copies to `docs/data/scored_tracts.geojson`
- Carries ALL 53 data columns (Baltimore-only supplementary columns present as nulls for non-Baltimore tracts)

### `app.js` — Modified (tooltip expanded)
- `showTooltip()` extended with three new sections below the core tract rows:
  - **Score Breakdown**: 8 sub-scores with weight annotations — only shown for scored tracts
  - **Additional Context**: stackability note (count and zone labels)
  - **Local Detail**: Baltimore-only parcel metrics if `land_to_value_ratio != null`, otherwise "Parcel-level data not available for this county"
- Added `fmtRat` formatter for ratio fields
- No changes to map rendering, selection, or form submission logic

### `docs/index.html` — Modified
- Methodology weight table updated: Investment Viability 52% → 55% (4 sub-rows), Community Need 33% → 45% (4 sub-rows), Stackability section removed
- Hard filter description updated: removed "AND zero building permits" from general description
- Weighted Scoring description updated: stackability described as supplementary context, not a scored dimension

---

## Data Sources & Actual Endpoints Used
All data was already on disk from Iteration 01. No new API calls this session.

---

## Results / Outputs

| Output | Details |
|---|---|
| `data/processed/md_tracts_filtered.csv` | 359 advance to scoring, 92 eliminated as Already Attractive, 0 Eliminated — Unviable |
| `data/output/scored_tracts.csv` | 451 rows, 53 columns, 113 recommended |
| `data/output/scored_tracts.geojson` | 451 features, 54 columns (includes geometry) |
| `docs/data/scored_tracts.geojson` | Copy for GitHub Pages site |

**Top 5 recommended tracts (V2):**
1. 24510040200 — Baltimore city, Already Attractive, score 0.684
2. 24510070400 — Baltimore city, Already Attractive, score 0.595
3. 24510060400 — Baltimore city, Goldilocks, score 0.593
4. 24510260605 — Baltimore city, Already Attractive, score 0.542
5. 24510260404 — Baltimore city, Already Attractive, score 0.533

**Recommended by classification:** Less Likely 77, Already Attractive 21, Goldilocks 15

---

## Key Technical Findings / Gotchas

1. **ACS data gaps in Urban Institute file**: `median_homevalue_2024` is null for 23 advancing tracts; `median_hhincome_2024` is null for 4. These are tracts with near-zero owner-occupied housing (renter-only or institutional). All 27 happen to be classified "Already Attractive" by the UI tool — they passed through the filter because our threshold comparison returns False for NaN. Imputed with advancing-tract median. **Consider adding these to the Already Attractive filter using UI classification as a fallback.**

2. **17 Goldilocks tracts eliminated as Already Attractive**: Our filter (income > metro median AND home value > top quartile) is catching tracts that the Urban Institute classifies as Goldilocks. This is a known tension — the UI classification uses national benchmarks while our filter uses Maryland-specific thresholds. Needs qualitative review before final recommendations.

3. **0 Unviable tracts caught**: No tracts satisfy `jobs < 200 AND pov > 0.45` simultaneously among the 451 eligible tracts. The filter logic is correct but finds no matches in this dataset.

4. **Scoring shift notable**: V2 recommended list has 77 Less Likely tracts vs fewer in V1. The new vacancy/home-value/ownership inputs favor low-value, high-vacancy neighborhoods over development-capacity signals from Baltimore parcel data. Worth reviewing whether the top Less Likely recommendations (ranks 8–20 are mostly Baltimore tracts with <400 jobs) are genuinely investment-viable.

5. **`app.js` is at repo root, not `docs/`**: For GitHub Pages serving from `docs/`, `app.js` needs to be at `docs/app.js`. Currently at root — site may not load on GitHub Pages until this is resolved.
