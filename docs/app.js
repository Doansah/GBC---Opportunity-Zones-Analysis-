/* ═══════════════════════════════════════════════════════════════════════════
   SPA Router — tab-based page navigation
   ═══════════════════════════════════════════════════════════════════════════ */

const VALID_PAGES = ['background', 'methodology', 'map', 'submit'];

function showPage(name) {
  if (!VALID_PAGES.includes(name)) name = 'background';

  document.querySelectorAll('.page[data-page]').forEach(div => {
    div.style.display = div.dataset.page === name ? 'block' : 'none';
  });

  document.querySelectorAll('.site-nav a[data-page]').forEach(a => {
    a.classList.toggle('nav-active', a.dataset.page === name);
  });

  if (name === 'map') {
    // Leaflet initialises on a hidden container — force correct size on reveal
    setTimeout(() => { if (typeof map !== 'undefined') map.invalidateSize(); }, 10);
  }

  window.scrollTo(0, 0);
}

function routeFromHash() {
  showPage(window.location.hash.replace('#', '') || 'background');
}

// Wire nav links and hero CTA
document.querySelectorAll('.site-nav a[data-page], .hero-cta[data-page]').forEach(a => {
  a.addEventListener('click', e => {
    e.preventDefault();
    window.location.hash = '#' + a.dataset.page;
  });
});

window.addEventListener('hashchange', routeFromHash);
document.addEventListener('DOMContentLoaded', routeFromHash);

/* ── Configuration ─────────────────────────────────────────────────────────── */
const FORMSPREE_ENDPOINT = 'https://formspree.io/f/xnjlgevo';
const GEOJSON_PATH       = 'data/scored_tracts.geojson';
const MAP_CENTER         = [38.95, -76.75];
const MAP_ZOOM           = 8;

/* ── Classification colors (match pipeline visualisation palette) ─────────── */
const CLASS_COLORS = {
  'Goldilocks':         '#1a9641',
  'Less Likely':        '#b0b0b0',
  'Already Attractive': '#fdae61',
};

/* ── Selected-tract highlight style ─────────────────────────────────────────── */
const SELECTED_STYLE = {
  color:       '#c9962a',
  weight:      3,
  fillColor:   '#c9962a',
  fillOpacity: 0.40,
};

/* ── Default base style ──────────────────────────────────────────────────── */
const BASE_BORDER = { color: '#ffffff', weight: 0.8, opacity: 0.8 };

/* ── State ───────────────────────────────────────────────────────────────── */
let currentMode    = 'score';          // 'score' | 'classification'
let geojsonLayer   = null;
let selectedTracts = new Map();        // geoid → { properties, layer }
let layerByGeoid   = new Map();        // geoid → Leaflet layer

/* ═══════════════════════════════════════════════════════════════════════════
   Color helpers
   ═══════════════════════════════════════════════════════════════════════════ */

/** Interpolate between #d73027 (red) → #fdae61 (orange) → #1a9641 (green)
 *  for composite_score in [0, 1]. Returns '#rrggbb'. */
function scoreToColor(score) {
  if (score == null || isNaN(score)) return '#cccccc';
  const t = Math.max(0, Math.min(1, score));
  let r, g, b;
  if (t < 0.5) {
    const u = t / 0.5;
    r = Math.round(215 + (253 - 215) * u);
    g = Math.round( 48 + (174 -  48) * u);
    b = Math.round( 39 + ( 97 -  39) * u);
  } else {
    const u = (t - 0.5) / 0.5;
    r = Math.round(253 + ( 26 - 253) * u);
    g = Math.round(174 + (150 - 174) * u);
    b = Math.round( 97 + ( 65 -  97) * u);
  }
  return `rgb(${r},${g},${b})`;
}

function classColor(cls) {
  return CLASS_COLORS[cls] || '#aaaaaa';
}

/* ═══════════════════════════════════════════════════════════════════════════
   Style function
   ═══════════════════════════════════════════════════════════════════════════ */

function styleFeature(feature) {
  const p   = feature.properties;
  const id  = p.geoid;
  if (selectedTracts.has(id)) return SELECTED_STYLE;

  const fill = currentMode === 'score'
    ? scoreToColor(p.composite_score)
    : classColor(p.classification);

  return { ...BASE_BORDER, fillColor: fill, fillOpacity: 0.72 };
}

/* ═══════════════════════════════════════════════════════════════════════════
   Tooltip
   ═══════════════════════════════════════════════════════════════════════════ */

const tooltip = document.getElementById('map-tooltip');

function showTooltip(e, p) {
  const fmtPct = v => (v != null ? (v * 100).toFixed(1) + '%' : 'N/A');
  const fmtNum = v => (v != null ? Number(v).toLocaleString() : 'N/A');
  const fmtDol = v => (v != null ? '$' + Number(v).toLocaleString() : 'N/A');
  const fmtSco = v => (v != null ? Number(v).toFixed(3) : 'N/A');
  const fmtRat = v => (v != null ? Number(v).toFixed(2) : 'N/A');

  const badgeClass = {
    'Goldilocks':         'goldilocks',
    'Already Attractive': 'already-att',
    'Less Likely':        'less-likely',
  }[p.classification] || '';

  // Score breakdown — only for tracts that were scored (not eliminated)
  const scored = p.composite_score != null;
  const scoreBreakdown = scored ? `
    <div class="tt-section">Score Breakdown</div>
    <div class="tt-row">
      <span class="tt-label">Job density</span>
      <span class="tt-val">${fmtSco(p.job_density_score)} <span class="tt-wt">(30%)</span></span>
    </div>
    <div class="tt-row">
      <span class="tt-label">Vacancy rate</span>
      <span class="tt-val">${fmtSco(p.vacancy_rate_score)} <span class="tt-wt">(10%)</span></span>
    </div>
    <div class="tt-row">
      <span class="tt-label">Home value</span>
      <span class="tt-val">${fmtSco(p.home_value_inv_score)} <span class="tt-wt">(10%)</span></span>
    </div>
    <div class="tt-row">
      <span class="tt-label">Ownership rate</span>
      <span class="tt-val">${fmtSco(p.ownership_inv_score)} <span class="tt-wt">(5%)</span></span>
    </div>
    <div class="tt-row">
      <span class="tt-label">Poverty</span>
      <span class="tt-val">${fmtSco(p.poverty_score)} <span class="tt-wt">(18%)</span></span>
    </div>
    <div class="tt-row">
      <span class="tt-label">Income</span>
      <span class="tt-val">${fmtSco(p.income_inv_score)} <span class="tt-wt">(12%)</span></span>
    </div>
    <div class="tt-row">
      <span class="tt-label">Unemployment</span>
      <span class="tt-val">${fmtSco(p.unemployment_score)} <span class="tt-wt">(8%)</span></span>
    </div>
    <div class="tt-row">
      <span class="tt-label">Education</span>
      <span class="tt-val">${fmtSco(p.education_inv_score)} <span class="tt-wt">(7%)</span></span>
    </div>
  ` : '';

  // Stackability — supplementary context, not a score component
  const stackNote = (p.stackability_count > 0)
    ? `Inside ${p.stackability_count} incentive zone(s)`
    : 'No overlapping incentive zones';

  // Baltimore-only parcel/permit detail (null for non-Baltimore tracts)
  const hasBaltDetail = p.land_to_value_ratio != null;
  const baltDetail = hasBaltDetail ? `
    <div class="tt-section">Local Detail (Baltimore)</div>
    <div class="tt-row">
      <span class="tt-label">Land/value ratio</span>
      <span class="tt-val">${fmtRat(p.land_to_value_ratio)}</span>
    </div>
    <div class="tt-row">
      <span class="tt-label">Vacancy proxy</span>
      <span class="tt-val">${fmtPct(p.vacancy_proxy)}</span>
    </div>
    <div class="tt-row">
      <span class="tt-label">Owner-occupancy</span>
      <span class="tt-val">${fmtPct(p.owner_occupancy_rate)}</span>
    </div>
    <div class="tt-row">
      <span class="tt-label">Commercial parcels</span>
      <span class="tt-val">${fmtPct(p.pct_commercial)}</span>
    </div>
  ` : `
    <div class="tt-section">Local Detail</div>
    <div class="tt-row tt-muted">Parcel-level data not available for this county.</div>
  `;

  tooltip.innerHTML = `
    <div class="tt-title">${p.geoid} &mdash; ${p.county}</div>
    <div class="tt-row">
      <span class="tt-label">Class</span>
      <span class="tt-val"><span class="t-badge ${badgeClass}">${p.classification}</span></span>
    </div>
    <div class="tt-row">
      <span class="tt-label">Score</span>
      <span class="tt-val">${fmtSco(p.composite_score)}</span>
    </div>
    <div class="tt-row">
      <span class="tt-label">Rank</span>
      <span class="tt-val">${p.rank != null ? '#' + p.rank : 'N/A'}</span>
    </div>
    <div class="tt-row">
      <span class="tt-label">Jobs (2022)</span>
      <span class="tt-val">${fmtNum(p.jobs_2022)}</span>
    </div>
    <div class="tt-row">
      <span class="tt-label">Poverty</span>
      <span class="tt-val">${fmtPct(p.povrate_2024)}</span>
    </div>
    <div class="tt-row">
      <span class="tt-label">Med. Income</span>
      <span class="tt-val">${fmtDol(p.median_hhincome_2024)}</span>
    </div>
    ${scoreBreakdown}
    <div class="tt-section">Additional Context</div>
    <div class="tt-row tt-muted">${stackNote}</div>
    ${baltDetail}
  `;
  tooltip.style.display = 'block';
  moveTooltip(e);
}

function moveTooltip(e) {
  const pad = 14;
  let x = e.clientX + pad;
  let y = e.clientY + pad;
  const w = tooltip.offsetWidth  || 240;
  const h = tooltip.offsetHeight || 180;
  if (x + w > window.innerWidth  - 8) x = e.clientX - w - pad;
  if (y + h > window.innerHeight - 8) y = e.clientY - h - pad;
  tooltip.style.left = x + 'px';
  tooltip.style.top  = y + 'px';
}

function hideTooltip() {
  tooltip.style.display = 'none';
}

/* ═══════════════════════════════════════════════════════════════════════════
   Selection sidebar
   ═══════════════════════════════════════════════════════════════════════════ */

function badgeClass(cls) {
  return { 'Goldilocks': 'goldilocks', 'Already Attractive': 'already-att', 'Less Likely': 'less-likely' }[cls] || '';
}

function updateSidebar() {
  const countEl = document.getElementById('selection-count');
  const listEl  = document.getElementById('tract-list');
  const emptyEl = document.getElementById('sidebar-empty');
  const submitCount = document.getElementById('submit-count');

  const n = selectedTracts.size;
  countEl.textContent  = n;
  if (submitCount) submitCount.textContent = n;

  if (n === 0) {
    listEl.innerHTML  = '';
    emptyEl.style.display = 'block';
    return;
  }
  emptyEl.style.display = 'none';

  listEl.innerHTML = '';
  selectedTracts.forEach(({ properties: p }, geoid) => {
    const div = document.createElement('div');
    div.className = 'tract-entry';
    div.innerHTML = `
      <div class="tract-info">
        <div class="t-id">${p.geoid}
          <span class="t-badge ${badgeClass(p.classification)}">${p.classification.split(' ')[0]}</span>
        </div>
        <div class="t-meta">${p.county} &mdash; Score ${p.composite_score != null ? (+p.composite_score).toFixed(3) : 'N/A'}</div>
      </div>
      <button class="remove-btn" data-geoid="${geoid}" title="Remove">&times;</button>
    `;
    listEl.appendChild(div);
  });

  // Wire remove buttons
  listEl.querySelectorAll('.remove-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.geoid;
      const entry = selectedTracts.get(id);
      if (entry) toggleTract(entry.layer, entry.layer.feature);
    });
  });
}

/* ═══════════════════════════════════════════════════════════════════════════
   localStorage persistence
   ═══════════════════════════════════════════════════════════════════════════ */

function saveSelections() {
  const data = [];
  selectedTracts.forEach(({ properties }, geoid) => {
    data.push([geoid, properties]);
  });
  localStorage.setItem('oz_selections', JSON.stringify(data));
}

function loadSavedGeoids() {
  try {
    const raw = localStorage.getItem('oz_selections');
    if (!raw) return new Set();
    const data = JSON.parse(raw);
    return new Set(data.map(([g]) => g));
  } catch (_) {
    return new Set();
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   Toggle tract selection
   ═══════════════════════════════════════════════════════════════════════════ */

function toggleTract(layer, feature) {
  const id = feature.properties.geoid;
  if (selectedTracts.has(id)) {
    selectedTracts.delete(id);
    layer.setStyle(styleFeature(feature));
    layer.bringToFront && layer.bringToFront();
  } else {
    selectedTracts.set(id, { properties: feature.properties, layer });
    layer.setStyle(SELECTED_STYLE);
    layer.bringToFront && layer.bringToFront();
  }
  updateSidebar();
  saveSelections();
}

/* ═══════════════════════════════════════════════════════════════════════════
   Map initialisation
   ═══════════════════════════════════════════════════════════════════════════ */

const map = L.map('map', { zoomControl: true }).setView(MAP_CENTER, MAP_ZOOM);

L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
  subdomains: 'abcd',
  maxZoom: 19,
}).addTo(map);

/* ── Build legend ─────────────────────────────────────────────────────────── */
const scoreLegendHTML = `
  <div class="map-legend" id="legend-score">
    <strong>Composite Score</strong>
    <div class="legend-gradient"></div>
    <div class="legend-gradient-labels"><span>Lower</span><span>Higher</span></div>
    <div class="legend-item" style="margin-top:0.5rem">
      <div class="legend-swatch" style="background:#c9962a;border-color:#a07820"></div>
      <span>Selected tract</span>
    </div>
  </div>
`;

const classLegendHTML = `
  <div class="map-legend" id="legend-class">
    <strong>Classification</strong>
    ${Object.entries(CLASS_COLORS).map(([label, color]) => `
      <div class="legend-item">
        <div class="legend-swatch" style="background:${color}"></div>
        <span>${label}</span>
      </div>
    `).join('')}
    <div class="legend-item">
      <div class="legend-swatch" style="background:#c9962a;border-color:#a07820"></div>
      <span>Selected</span>
    </div>
  </div>
`;

const LegendControl = L.Control.extend({
  onAdd() {
    const div = L.DomUtil.create('div');
    div.id = 'leaflet-legend';
    div.innerHTML = scoreLegendHTML;
    return div;
  }
});
const legendControl = new LegendControl({ position: 'bottomleft' });
legendControl.addTo(map);

function updateLegend() {
  const el = document.getElementById('leaflet-legend');
  if (!el) return;
  el.innerHTML = currentMode === 'score' ? scoreLegendHTML : classLegendHTML;
}

/* ═══════════════════════════════════════════════════════════════════════════
   Incentive Zone Layer Panel
   ═══════════════════════════════════════════════════════════════════════════ */

const IMAP_LAYERS = [
  { id: 'enterprise_zones',            label: 'Enterprise Zones',          color: '#e63946' },
  { id: 'enterprise_zone_focus_areas', label: 'EZ Focus Areas',            color: '#f4845f' },
  { id: 'sustainable_communities',     label: 'Sustainable Communities',   color: '#2a9d8f' },
  { id: 'rise_zones',                  label: 'RISE Zones',                color: '#9b5de5' },
  { id: 'opportunity_zones',           label: 'Opportunity Zones (Fed.)',  color: '#0077b6' },
  { id: 'qualified_census_tracts',     label: 'Qualified Census Tracts',   color: '#ff9f1c' },
];

const imapLeafletLayers = {};
const imapLoadState    = {};
IMAP_LAYERS.forEach(d => { imapLeafletLayers[d.id] = null; imapLoadState[d.id] = 'idle'; });

const LayerPanelControl = L.Control.extend({
  onAdd(map) {
    const container = L.DomUtil.create('div', 'leaflet-layer-panel');
    container.innerHTML = `
      <div id="layer-panel-header">
        Incentive Zones <span class="panel-toggle-icon">&#9650;</span>
      </div>
      <div id="layer-panel-body"></div>`;

    container.querySelector('#layer-panel-header').addEventListener('click', () => {
      container.classList.toggle('collapsed');
    });

    const body = container.querySelector('#layer-panel-body');
    IMAP_LAYERS.forEach(def => {
      const row = document.createElement('label');
      row.className = 'layer-row';
      row.innerHTML = `
        <input type="checkbox" id="layer-cb-${def.id}" data-layer-id="${def.id}" />
        <span class="layer-swatch" style="background:${def.color}22;border-color:${def.color}"></span>
        <span class="layer-label">${def.label}</span>`;
      body.appendChild(row);
      row.querySelector('input').addEventListener('change', e => handleLayerToggle(def, e.target.checked));
    });

    L.DomEvent.disableClickPropagation(container);
    L.DomEvent.disableScrollPropagation(container);
    return container;
  }
});

new LayerPanelControl({ position: 'topright' }).addTo(map);

async function handleLayerToggle(def, isOn) {
  if (!isOn) {
    if (imapLeafletLayers[def.id]) map.removeLayer(imapLeafletLayers[def.id]);
    return;
  }
  if (imapLoadState[def.id] === 'idle') await loadImapLayer(def);
  if (imapLeafletLayers[def.id] && imapLoadState[def.id] === 'loaded') {
    imapLeafletLayers[def.id].addTo(map);
  }
}

async function loadImapLayer(def) {
  imapLoadState[def.id] = 'loading';
  setLayerStatus(def.id, 'loading');
  try {
    const resp = await fetch('data/imap/' + def.id + '.geojson');
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    imapLeafletLayers[def.id] = L.geoJSON(data, {
      interactive: false,   // clicks pass through to tract layer below
      style: {
        color:       def.color,
        weight:      2,
        opacity:     0.85,
        fillColor:   def.color,
        fillOpacity: 0.12,
      },
    });
    imapLoadState[def.id] = 'loaded';
    setLayerStatus(def.id, 'loaded');
  } catch (err) {
    imapLoadState[def.id] = 'error';
    setLayerStatus(def.id, 'error');
    const cb = document.getElementById('layer-cb-' + def.id);
    if (cb) cb.checked = false;
    console.error('Failed to load iMAP layer ' + def.id + ':', err);
  }
}

function setLayerStatus(id, status) {
  const row = document.querySelector('[data-layer-id="' + id + '"]')?.closest('.layer-row');
  if (!row) return;
  row.querySelectorAll('.layer-loading, .layer-error').forEach(el => el.remove());
  if (status === 'loading') {
    const s = document.createElement('span'); s.className = 'layer-loading'; s.textContent = '…'; row.appendChild(s);
  } else if (status === 'error') {
    const s = document.createElement('span'); s.className = 'layer-error';   s.textContent = '✕'; row.appendChild(s);
  }
}

/* ── Track mouse for tooltip ──────────────────────────────────────────────── */
document.addEventListener('mousemove', e => {
  if (tooltip.style.display === 'block') moveTooltip(e);
});

/* ── Load GeoJSON ─────────────────────────────────────────────────────────── */
const savedGeoids = loadSavedGeoids();

fetch(GEOJSON_PATH)
  .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
  .then(data => {
    geojsonLayer = L.geoJSON(data, {
      style:         styleFeature,
      onEachFeature: (feature, layer) => {
        const id = feature.properties.geoid;
        layerByGeoid.set(id, layer);

        // Restore saved selection
        if (savedGeoids.has(id)) {
          selectedTracts.set(id, { properties: feature.properties, layer });
          layer.setStyle(SELECTED_STYLE);
        }

        layer.on({
          mouseover(e) {
            if (!selectedTracts.has(id)) {
              layer.setStyle({ weight: 2, color: '#333', fillOpacity: 0.85 });
            }
            showTooltip(e.originalEvent, feature.properties);
            layer.bringToFront();
          },
          mousemove(e) { moveTooltip(e.originalEvent); },
          mouseout() {
            geojsonLayer.resetStyle(layer);
            if (selectedTracts.has(id)) layer.setStyle(SELECTED_STYLE);
            hideTooltip();
          },
          click() { toggleTract(layer, feature); },
        });
      },
    }).addTo(map);

    updateSidebar();
    map.invalidateSize();
    console.log(`Loaded ${data.features.length} tract features`);
  })
  .catch(err => {
    console.error('Failed to load GeoJSON:', err);
    document.getElementById('map').insertAdjacentHTML('beforeend',
      `<div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,0.85);z-index:9;font-size:0.95rem;color:#721c24;padding:1rem;text-align:center">
        <span>Could not load map data. If running locally, use <code>python3 -m http.server 8080</code> instead of opening the file directly.</span>
       </div>`
    );
  });

/* ═══════════════════════════════════════════════════════════════════════════
   View toggle
   ═══════════════════════════════════════════════════════════════════════════ */

document.getElementById('btn-score').addEventListener('click', () => {
  currentMode = 'score';
  document.getElementById('btn-score').classList.add('active');
  document.getElementById('btn-class').classList.remove('active');
  if (geojsonLayer) geojsonLayer.setStyle(styleFeature);
  // Re-apply selected highlight (setStyle overwrites everything)
  selectedTracts.forEach(({ layer, properties: p }) => {
    layer.setStyle(SELECTED_STYLE);
  });
  updateLegend();
});

document.getElementById('btn-class').addEventListener('click', () => {
  currentMode = 'classification';
  document.getElementById('btn-class').classList.add('active');
  document.getElementById('btn-score').classList.remove('active');
  if (geojsonLayer) geojsonLayer.setStyle(styleFeature);
  selectedTracts.forEach(({ layer }) => layer.setStyle(SELECTED_STYLE));
  updateLegend();
});

/* ═══════════════════════════════════════════════════════════════════════════
   Sidebar collapse toggle
   ═══════════════════════════════════════════════════════════════════════════ */

document.getElementById('sidebar-toggle').addEventListener('click', () => {
  const sidebar = document.getElementById('sidebar');
  const btn     = document.getElementById('sidebar-toggle');
  sidebar.classList.toggle('collapsed');
  btn.textContent = sidebar.classList.contains('collapsed') ? '›' : '‹';
  // Invalidate map size after sidebar width changes
  setTimeout(() => map.invalidateSize(), 210);
});

/* ═══════════════════════════════════════════════════════════════════════════
   Form submission
   ═══════════════════════════════════════════════════════════════════════════ */

document.getElementById('submit-btn').addEventListener('click', async () => {
  const nameEl  = document.getElementById('field-name');
  const orgEl   = document.getElementById('field-org');
  const commEl  = document.getElementById('field-comments');
  const msgEl   = document.getElementById('form-message');
  const btn     = document.getElementById('submit-btn');

  msgEl.className = 'form-message';
  msgEl.textContent = '';

  if (!nameEl.value.trim()) {
    msgEl.className = 'form-message error';
    msgEl.textContent = 'Please enter your name before submitting.';
    nameEl.focus();
    return;
  }

  if (selectedTracts.size === 0) {
    msgEl.className = 'form-message error';
    msgEl.textContent = 'Please select at least one tract on the map before submitting.';
    return;
  }

  const payload = {
    name:         nameEl.value.trim(),
    organization: orgEl.value.trim(),
    comments:     commEl.value.trim(),
    selections:   [...selectedTracts.values()].map(({ properties: p }) => ({
      geoid:           p.geoid,
      county:          p.county,
      classification:  p.classification,
      composite_score: p.composite_score,
      rank:            p.rank,
    })),
    selection_count: selectedTracts.size,
    submitted_at:    new Date().toISOString(),
  };

  btn.disabled    = true;
  btn.textContent = 'Submitting…';

  try {
    const resp = await fetch(FORMSPREE_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (resp.ok) {
      msgEl.className   = 'form-message success';
      msgEl.textContent = `Thank you, ${payload.name}! Your selections (${payload.selection_count} tracts) have been submitted successfully.`;
      // Clear selections
      selectedTracts.forEach(({ layer, properties: p }, id) => {
        const feature = layerByGeoid.get(id);
        if (feature && geojsonLayer) geojsonLayer.resetStyle(feature);
      });
      selectedTracts.clear();
      localStorage.removeItem('oz_selections');
      updateSidebar();
      // Clear form
      nameEl.value = '';
      orgEl.value  = '';
      commEl.value = '';
    } else {
      const body = await resp.json().catch(() => ({}));
      throw new Error(body.error || `Server error ${resp.status}`);
    }
  } catch (err) {
    msgEl.className   = 'form-message error';
    msgEl.textContent = `Submission failed: ${err.message}. Please try again or contact us directly.`;
  } finally {
    btn.disabled    = false;
    btn.textContent = 'Submit Selections';
  }
});
