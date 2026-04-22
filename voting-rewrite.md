Project: OZ Stakeholder Voting Site
You are building an interactive static website deployed on GitHub Pages (doansah.github.io/GBC---Opportunity-Zones-Analysis-/). The site serves two purposes: (1) present the Opportunity Zones research methodology and findings to stakeholders, and (2) let stakeholders interactively select census tracts they support for OZ designation and submit their selections.
Branch: Work on a branch called site (or gh-pages), separate from main which contains the data pipeline.
Tech stack: Static HTML/CSS/JS. Leaflet.js for the map (NOT Folium — we need full control over click interactions). No frameworks (no React, no build step). The site must work as a static GitHub Pages deployment with no server-side code.
Data input: A single GeoJSON file (data/scored_tracts.geojson) containing all 451 Maryland eligible census tracts with their polygon geometries and properties including: geoid, county, classification (Goldilocks / Less Likely / Already Attractive), composite_score, rank, recommended (0/1), jobs_2022, povrate_2024, median_hhincome_2024, vacancyrate_2024, stackability_count, and all seven sub-scores. This file is the output of the data pipeline on the main branch — it gets copied into the site branch manually when the data updates.
Site structure (single page, scrollable sections):

Hero / Header — Project title "Opportunity Zones 2.0: Maryland Tract Analysis", GBC branding, brief tagline.
Background section — 2–3 paragraphs explaining what Opportunity Zones are, why the 2027 re-designation matters, and what this project does. Keep it concise and accessible for a non-technical audience.
Methodology section — Brief explanation of the three-stage evaluation (filter → score → recommend). Include a simple visual or table showing the scoring weight breakdown: Investment Viability 52% (jobs 30%, development capacity 12%, market momentum 10%), Community Need 33% (poverty 15%, income 10%, unemployment 8%), Stackability 15%. Explain the Goldilocks concept in plain language.
Interactive Map section — Full-width Leaflet map. This is the core feature.

Load tract polygons from the GeoJSON file.
Default choropleth coloring by composite_score (gradient from red/low to green/high) or by classification (three distinct colors for Goldilocks, Less Likely, Already Attractive). Include a toggle to switch between these two views.
Click to select: When a user clicks a tract, it toggles a "selected" state — the polygon gets a distinct highlight (thick border, fill color change, or hatch pattern) so it's visually obvious against the choropleth. Clicking again deselects it.
Hover popup: On hover (not click), show a compact tooltip with: tract geoid, county, classification, composite score, rank, and 2–3 key metrics (jobs, poverty rate, median income).
Selection sidebar or panel: A collapsible panel (right side or bottom) that shows the running list of selected tracts. Each entry shows the geoid, county, and a remove button (×). The panel header shows the count of selections. This list updates in real time as the user clicks tracts on the map.
Persist selections in localStorage so they survive page refresh.


Submit section — Below or integrated with the map.

Text fields for: stakeholder name, organization, and an optional comments box.
A "Submit Selections" button that POSTs the data to a Formspree endpoint (or similar headless form service). The payload should be JSON: {name, organization, comments, selections: [{geoid, county, classification, composite_score}, ...], submitted_at: ISO timestamp}.
On successful submission, show a confirmation message and clear the selections from localStorage.
The Formspree endpoint URL should be configurable (stored as a constant at the top of the JS file) so it can be swapped without searching through code.


Footer — Data sources, date, GBC attribution.

Design requirements:

Professional, clean, modern. Dark header/hero, light body sections. Use a restrained color palette — navy/dark blue for headers, white/light gray for content areas, gold accent for highlights.
Responsive — the map should work on tablet screens (stakeholders may use iPads). On mobile, the selection sidebar should collapse to a bottom sheet or full-screen overlay.
Typography: use a clean sans-serif (system fonts or Google Fonts like DM Sans or Source Sans 3). Body text 16px, comfortable line height.
The map should be at least 70vh tall on desktop.
No excessive animations. Professional tone throughout.

Key technical decisions:

Use Leaflet.js loaded from CDN (unpkg or cdnjs). No npm, no build step.
GeoJSON file loaded via fetch() — keep it as a separate file, not inlined in the HTML.
All JS in a single app.js file or inline in the HTML. Keep it simple.
CSS can be inline in <style> or a single style.css file.
For Formspree: the free tier accepts submissions via POST https://formspree.io/f/{form_id} with JSON body and Content-Type: application/json header.

What NOT to build:

No user authentication. This is an open page — anyone with the link can submit. That's fine for our use case.
No real-time aggregation dashboard showing other people's votes. That's a separate future feature.
No backend. Everything is client-side except the Formspree POST.

File structure for the site branch:
/
├── index.html
├── style.css (optional — can be inline)
├── app.js (optional — can be inline)
├── data/
│   └── scored_tracts.geojson
└── assets/
    └── (any images, logos)
First step: Generate the scored_tracts.geojson from the pipeline output. This requires joining the scored CSV (data/output/scored_tracts.csv) with the tract boundary shapefile (census_tract_shape_files/tl_2025_24_tract.shp), filtering to Maryland's 451 eligible tracts, and exporting as GeoJSON with all score columns as feature properties. Write a script for this on the main branch (scripts/11_export_geojson.py), then copy the resulting file to the site branch.
Second step: Build the static site (index.html + supporting files) on the site branch.