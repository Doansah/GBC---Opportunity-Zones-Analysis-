"""
11_visualize.py

Produces four static PNG maps and one interactive folium HTML explorer
for Maryland's 451 eligible OZ census tracts.

Outputs:
  data/output/maps/01_investment_heat.png
  data/output/maps/02_community_need.png
  data/output/maps/03_stackability.png
  data/output/maps/04_composite_score.png
  data/output/maps/oz_explorer.html

Dependencies beyond requirements.txt: matplotlib, folium
  pip install matplotlib folium
"""

from __future__ import annotations

import json
from pathlib import Path

import folium
import geopandas as gpd
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from mpl_toolkits.axes_grid1 import make_axes_locatable

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT          = Path(__file__).resolve().parent.parent
SCORED_CSV    = ROOT / "data" / "output" / "scored_tracts.csv"
SHP_PATH      = ROOT / "census_tract_shape_files" / "tl_2025_24_tract.shp"
ELIGIBLE_CSV  = ROOT / "data" / "raw" / "eligible_census_tracts.csv"
OUT_DIR       = ROOT / "data" / "output" / "maps"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Visual constants ──────────────────────────────────────────────────────────
FIG_SIZE        = (12, 10)
DPI             = 200
FACECOLOR       = "white"
ELIMINATED_GRAY = "#cccccc"
CAPTION_FONTSIZE = 8
CAPTION_COLOR    = "#555555"

CLASS_COLORS = {
    "Goldilocks":         "#1a9641",
    "Already Attractive": "#fdae61",
    "Less Likely":        "#d3d3d3",
}
STACK_COLORS = {0: "#f0f0f0", 1: "#9ecae1", 2: "#2171b5"}

TARGET_DESIGNATIONS = 113
TOP_N_ANNOTATE      = 10
TOP_N_MARKERS       = 20


# ── Data loading ──────────────────────────────────────────────────────────────

def load_and_merge() -> gpd.GeoDataFrame:
    """Load scored_tracts.csv and TIGER shapefile; merge on GEOID."""
    print(f"Loading scored tracts from {SCORED_CSV}…")
    scored = pd.read_csv(SCORED_CSV, dtype={"geoid": str})
    scored["geoid"] = scored["geoid"].str.zfill(11)
    print(f"  {len(scored)} rows loaded")

    print(f"Loading shapefile from {SHP_PATH}…")
    tracts_shp = gpd.read_file(SHP_PATH)
    tracts_shp["GEOID"] = tracts_shp["GEOID"].str.zfill(11)
    print(f"  {len(tracts_shp)} tract polygons loaded, CRS={tracts_shp.crs}")

    gdf = tracts_shp.merge(scored, left_on="GEOID", right_on="geoid", how="inner")
    gdf = gdf[gdf["stage1_result"].notna()].copy()
    gdf["rank"] = gdf["rank"].astype("Int64")
    print(f"  Merged GeoDataFrame: {len(gdf)} rows")
    return gdf


# ── Shared map helpers ────────────────────────────────────────────────────────

def _setup_map(title: str, caption: str):
    fig, ax = plt.subplots(1, 1, figsize=FIG_SIZE, facecolor=FACECOLOR)
    ax.set_facecolor(FACECOLOR)
    ax.axis("off")
    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
    fig.text(
        0.5, 0.02, caption,
        ha="center", va="bottom",
        fontsize=CAPTION_FONTSIZE, color=CAPTION_COLOR,
    )
    return fig, ax


def _add_colorbar(ax, cmap: str, vmin: float, vmax: float, label: str) -> None:
    divider = make_axes_locatable(ax)
    cax = divider.append_axes("right", size="3%", pad=0.1)
    sm = ScalarMappable(cmap=cmap, norm=Normalize(vmin=vmin, vmax=vmax))
    sm.set_array([])
    plt.colorbar(sm, cax=cax, label=label)


def _plot_state_boundary(ax, state_boundary: gpd.GeoDataFrame) -> None:
    state_boundary.boundary.plot(ax=ax, color="black", linewidth=0.8, zorder=5)


# ── Map 1: Investment heat ────────────────────────────────────────────────────

def map_investment_heat(
    advancing: gpd.GeoDataFrame,
    eliminated: gpd.GeoDataFrame,
    recommended: gpd.GeoDataFrame,
    state_boundary: gpd.GeoDataFrame,
    out_path: Path,
) -> None:
    title   = "Investment viability — job density + market momentum"
    caption = (
        "Color: job density score (0–1, YlOrRd).  "
        "Bold outline: top-113 recommended tracts.  "
        "Gray: eliminated from scoring (already attractive).\n"
        "Source: Urban Institute OZ Tool, Baltimore permit data (2026)"
    )
    fig, ax = _setup_map(title, caption)

    eliminated.plot(ax=ax, color=ELIMINATED_GRAY, linewidth=0.2, edgecolor="white")
    advancing.plot(
        ax=ax, column="job_density_score",
        cmap="YlOrRd", vmin=0.0, vmax=1.0,
        linewidth=0.2, edgecolor="white",
        missing_kwds={"color": ELIMINATED_GRAY},
    )
    recommended.plot(ax=ax, facecolor="none", edgecolor="black", linewidth=1.5)
    _plot_state_boundary(ax, state_boundary)
    _add_colorbar(ax, "YlOrRd", 0.0, 1.0, "Job density score")

    fig.savefig(out_path, dpi=DPI, bbox_inches="tight", facecolor=FACECOLOR)
    plt.close(fig)
    print(f"  Saved {out_path.name}")


# ── Map 2: Community need ─────────────────────────────────────────────────────

def map_community_need(
    gdf: gpd.GeoDataFrame,
    advancing: gpd.GeoDataFrame,
    state_boundary: gpd.GeoDataFrame,
    out_path: Path,
) -> None:
    title   = "Community need — poverty rate (2024)"
    caption = (
        "Color: poverty rate, OrRd (10–45% range shown).  "
        "Dark outline: Goldilocks poverty band (20–35%).  "
        "Gray: outside 10–45% range or eliminated from scoring.\n"
        "Source: ACS 5-Year Estimates 2020-2024"
    )
    fig, ax = _setup_map(title, caption)

    eliminated = gdf[gdf["stage1_result"] != "Advances to Scoring"].copy()
    eliminated.plot(ax=ax, color=ELIMINATED_GRAY, linewidth=0.2, edgecolor="white")

    in_band  = advancing[advancing["povrate_2024"].between(0.10, 0.45)].copy()
    out_band = advancing[~advancing["povrate_2024"].between(0.10, 0.45)].copy()

    out_band.plot(ax=ax, color=ELIMINATED_GRAY, linewidth=0.2, edgecolor="white")
    in_band.plot(
        ax=ax, column="povrate_2024",
        cmap="OrRd", vmin=0.10, vmax=0.45,
        linewidth=0.2, edgecolor="white",
    )

    goldilocks_band = advancing[advancing["povrate_2024"].between(0.20, 0.35)].copy()
    goldilocks_band.plot(ax=ax, facecolor="none", edgecolor="#333333", linewidth=1.0)

    _plot_state_boundary(ax, state_boundary)
    _add_colorbar(ax, "OrRd", 0.10, 0.45, "Poverty rate")

    fig.savefig(out_path, dpi=DPI, bbox_inches="tight", facecolor=FACECOLOR)
    plt.close(fig)
    print(f"  Saved {out_path.name}")


# ── Map 3: Stackability ───────────────────────────────────────────────────────

def map_stackability(
    gdf: gpd.GeoDataFrame,
    state_boundary: gpd.GeoDataFrame,
    out_path: Path,
) -> None:
    title   = "Incentive zone stackability (Enterprise / Sustainable Communities / RISE)"
    caption = (
        "Number of Maryland incentive zone programs overlapping each census tract.  "
        "Higher stacking = more leverage for developers.\n"
        "Source: MD iMAP Incentive Zones"
    )
    fig, ax = _setup_map(title, caption)

    for count_val, color in STACK_COLORS.items():
        subset = gdf[gdf["stackability_count"] == count_val]
        if len(subset) == 0:
            continue
        subset.plot(ax=ax, color=color, linewidth=0.2, edgecolor="white")

    _plot_state_boundary(ax, state_boundary)

    legend_patches = [
        mpatches.Patch(facecolor=STACK_COLORS[0], edgecolor="#aaaaaa", label="0 zones"),
        mpatches.Patch(facecolor=STACK_COLORS[1], edgecolor="#aaaaaa", label="1 zone"),
        mpatches.Patch(facecolor=STACK_COLORS[2], edgecolor="#aaaaaa", label="2 zones"),
    ]
    ax.legend(
        handles=legend_patches,
        loc="lower right",
        framealpha=0.9,
        fontsize=9,
        title="Stacked zones",
        title_fontsize=9,
    )

    fig.savefig(out_path, dpi=DPI, bbox_inches="tight", facecolor=FACECOLOR)
    plt.close(fig)
    print(f"  Saved {out_path.name}")


# ── Map 4: Composite score ────────────────────────────────────────────────────

def map_composite_score(
    advancing: gpd.GeoDataFrame,
    eliminated: gpd.GeoDataFrame,
    recommended: gpd.GeoDataFrame,
    top10: gpd.GeoDataFrame,
    state_boundary: gpd.GeoDataFrame,
    out_path: Path,
) -> None:
    title   = "Composite score — 113 recommended designations"
    caption = (
        "Color: composite score, RdYlGn (higher = stronger candidate).  "
        "Bold outline: top-113 recommended tracts.  Numbers: rank 1–10.\n"
        "Source: Composite of Urban Institute, SDAT, permit, and iMAP data"
    )
    fig, ax = _setup_map(title, caption)

    vmin = float(advancing["composite_score"].min())
    vmax = float(advancing["composite_score"].max())

    eliminated.plot(ax=ax, color=ELIMINATED_GRAY, linewidth=0.2, edgecolor="white")
    advancing.plot(
        ax=ax, column="composite_score",
        cmap="RdYlGn", vmin=vmin, vmax=vmax,
        linewidth=0.2, edgecolor="white",
        missing_kwds={"color": ELIMINATED_GRAY},
    )
    recommended.plot(ax=ax, facecolor="none", edgecolor="black", linewidth=1.5)
    _plot_state_boundary(ax, state_boundary)
    _add_colorbar(ax, "RdYlGn", vmin, vmax, "Composite score")

    for _, row in top10.iterrows():
        centroid = row.geometry.centroid
        ax.annotate(
            text=str(int(row["rank"])),
            xy=(centroid.x, centroid.y),
            ha="center", va="center",
            fontsize=6, fontweight="bold", color="black",
            zorder=10,
            bbox=dict(boxstyle="round,pad=0.15", fc="white", alpha=0.65, lw=0),
        )

    fig.savefig(out_path, dpi=DPI, bbox_inches="tight", facecolor=FACECOLOR)
    plt.close(fig)
    print(f"  Saved {out_path.name}")


# ── Incentive zone layer config ───────────────────────────────────────────────
# (filename, display name, fill color, border color, tooltip fields, aliases)
INCENTIVE_ZONE_LAYERS = [
    (
        "enterprise_zones.geojson",
        "Enterprise Zones",
        "#2c7fb8", "#1d5f8a",
        ["sitename", "county", "city"],
        ["Zone Name", "County", "City"],
    ),
    (
        "sustainable_communities.geojson",
        "Sustainable Communities",
        "#31a354", "#1f7035",
        ["Name", "County", "Acreage"],
        ["Community Name", "County", "Acreage (ac)"],
    ),
    (
        "rise_zones.geojson",
        "RISE Zones",
        "#756bb1", "#4a3d8f",
        ["ZONE_NAME", "COUNTY", "CITY"],
        ["Zone Name", "County", "City"],
    ),
    (
        "Qualified_Census_Tracts.geojson",
        "Qualified Census Tracts (QCT/LIHTC)",
        "#fd8d3c", "#d45e00",
        ["COUNTY_N", "GEOID20"],
        ["County", "Tract GEOID"],
    ),
    (
        "MDOT_Designated_TOD_Boundaries.geojson",
        "Transit Oriented Development (TOD)",
        "#e31a1c", "#a50f15",
        ["Station_Na", "County", "Des_Category"],
        ["Station", "County", "Category"],
    ),
]

IMAP_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "imap_incentive_zones"


# ── Folium interactive HTML ───────────────────────────────────────────────────

def build_folium_map(
    gdf: gpd.GeoDataFrame,
    advancing: gpd.GeoDataFrame,
    recommended: gpd.GeoDataFrame,
    top20_goldilocks: gpd.GeoDataFrame,
    out_path: Path,
) -> None:
    print("  Building folium map...")

    # Reproject to WGS84 (folium requires EPSG:4326)
    gdf_4326       = gdf.to_crs(epsg=4326)
    advancing_4326 = advancing.to_crs(epsg=4326)
    rec_4326       = recommended.to_crs(epsg=4326)
    top20_4326     = top20_goldilocks.to_crs(epsg=4326)

    # ── Base map ──────────────────────────────────────────────────────────────
    m = folium.Map(
        location=[39.0, -76.8],
        zoom_start=8,
        tiles="CartoDB positron",
        control_scale=True,
    )

    # ── Layer 1: Composite score choropleth (advancing tracts) ────────────────
    choropleth_data = (
        advancing_4326[["geoid", "composite_score"]]
        .dropna(subset=["composite_score"])
    )
    adv_geo = json.loads(
        advancing_4326[["geoid", "composite_score", "geometry"]].to_json()
    )

    folium.Choropleth(
        geo_data=adv_geo,
        data=choropleth_data,
        columns=["geoid", "composite_score"],
        key_on="feature.properties.geoid",
        fill_color="YlOrRd",
        fill_opacity=0.7,
        line_opacity=0.2,
        nan_fill_color="#f0f0f0",
        nan_fill_opacity=0.4,
        bins=6,
        legend_name="Composite Score (advancing tracts)",
        name="Composite Score Choropleth",
        highlight=True,
    ).add_to(m)

    # ── Layer 2: Eligible Census Tracts via EIG (hidden by default) ──────────
    if ELIGIBLE_CSV.exists():
        eligible_df = pd.read_csv(ELIGIBLE_CSV, dtype={"Census Tract Number": str})
        eligible_df["geoid"] = eligible_df["Census Tract Number"].str.zfill(11)
        eligible_df = eligible_df.rename(columns={
            "Census Tract Number": "tract_number",
            "Rural Status":        "rural_status",
        })

        eligible_gdf = gdf_4326.merge(
            eligible_df[["geoid", "rural_status"]],
            on="geoid",
            how="inner",
        )
        eligible_geo = json.loads(
            eligible_gdf[["geoid", "county", "rural_status", "geometry"]].to_json()
        )

        def style_eligible(_feature):
            return {
                "fillColor": "#4292c6",
                "color":     "#08519c",
                "weight":    1.0,
                "fillOpacity": 0.20,
            }

        folium.GeoJson(
            data=eligible_geo,
            name="Eligible Census Tracts via EIG",
            style_function=style_eligible,
            highlight_function=lambda _f: {"fillOpacity": 0.45, "weight": 2.0},
            tooltip=folium.GeoJsonTooltip(
                fields=["geoid", "county", "rural_status"],
                aliases=["GEOID", "County", "Rural Status"],
                localize=True,
                sticky=False,
            ),
            show=False,
        ).add_to(m)
        print(f"  Added 'Eligible Census Tracts via EIG' ({len(eligible_gdf)} tracts)")
    else:
        print(f"  WARNING: {ELIGIBLE_CSV} not found — skipping eligible tracts layer")

    # ── Layer 3: All 451 tracts, colored by UI classification (hidden) ────────
    color_map = (
        gdf_4326.set_index("geoid")["classification"]
        .map(CLASS_COLORS)
        .to_dict()
    )

    def style_all(feature):
        geoid = feature["properties"].get("geoid", "")
        fill  = color_map.get(geoid, "#cccccc")
        return {
            "fillColor": fill,
            "color": "#888888",
            "weight": 0.4,
            "fillOpacity": 0.3,
        }

    all_geo = json.loads(
        gdf_4326[["geoid", "classification", "geometry"]].to_json()
    )
    folium.GeoJson(
        data=all_geo,
        name="Urban Institute classification",
        style_function=style_all,
        show=False,
    ).add_to(m)

    # ── Layers 3–7: Individual incentive zone overlays (all hidden by default) ─
    for fname, layer_name, fill_color, border_color, tt_fields, tt_aliases in INCENTIVE_ZONE_LAYERS:
        zone_path = IMAP_DIR / fname
        if not zone_path.exists():
            print(f"  WARNING: {fname} not found — skipping layer '{layer_name}'")
            continue

        with open(zone_path, encoding="utf-8") as f:
            zone_geo = json.load(f)

        feature_count = len(zone_geo.get("features", []))
        print(f"  Adding layer '{layer_name}' ({feature_count} features)")

        # Only include tooltip fields that actually exist in this file's properties
        sample_props = {}
        if zone_geo.get("features"):
            sample_props = zone_geo["features"][0].get("properties", {})
        valid_fields   = [f for f in tt_fields  if f in sample_props]
        valid_aliases  = [tt_aliases[i] for i, f in enumerate(tt_fields) if f in sample_props]

        zone_style = {
            "fillColor":   fill_color,
            "color":       border_color,
            "weight":      1.5,
            "fillOpacity": 0.25,
        }
        zone_highlight = {
            "fillOpacity": 0.55,
            "weight":      2.5,
        }

        layer_kwargs = dict(
            data=zone_geo,
            name=layer_name,
            style_function=lambda _f, s=zone_style: s,
            highlight_function=lambda _f, h=zone_highlight: h,
            show=False,
        )
        if valid_fields:
            layer_kwargs["tooltip"] = folium.GeoJsonTooltip(
                fields=valid_fields,
                aliases=valid_aliases,
                localize=True,
                sticky=False,
            )

        folium.GeoJson(**layer_kwargs).add_to(m)

    # ── Layer 8: Recommended tracts (bold black outline) with hover tooltip ───
    tooltip_cols = [
        "geoid", "county", "classification", "composite_score", "rank",
        "jobs_2022", "povrate_2024", "stackability_count",
    ]
    rec_display = rec_4326[tooltip_cols + ["geometry"]].copy()
    rec_display["composite_score"] = rec_display["composite_score"].round(3)
    rec_display["povrate_pct"] = (rec_display["povrate_2024"] * 100).round(1).astype(str) + "%"
    rec_display["rank"] = rec_display["rank"].astype(str)

    def style_recommended(_feature):
        return {
            "fillColor": "transparent",
            "color": "#000000",
            "weight": 2.0,
            "fillOpacity": 0.0,
        }

    rec_geo = json.loads(rec_display.to_json())
    folium.GeoJson(
        data=rec_geo,
        name="Recommended designations (113)",
        style_function=style_recommended,
        highlight_function=lambda _x: {"weight": 3, "color": "#333333"},
        tooltip=folium.GeoJsonTooltip(
            fields=[
                "geoid", "county", "classification",
                "composite_score", "rank",
                "jobs_2022", "povrate_pct", "stackability_count",
            ],
            aliases=[
                "GEOID", "County", "Classification",
                "Composite Score", "Rank",
                "Jobs (2022)", "Poverty Rate", "Stackability",
            ],
            localize=True,
            sticky=False,
        ),
    ).add_to(m)

    # ── Layer 9: Top 20 Goldilocks CircleMarkers with popup table ─────────────
    top20_layer = folium.FeatureGroup(name="Top 20 Goldilocks tracts")
    for _, row in top20_4326.iterrows():
        centroid = row.geometry.centroid
        inc_val   = f"${int(row['median_hhincome_2024']):,}" if pd.notna(row.get("median_hhincome_2024")) else "N/A"
        pov_pct   = f"{row['povrate_2024'] * 100:.1f}%"     if pd.notna(row.get("povrate_2024"))         else "N/A"
        unemp_pct = f"{row['unemprate_2024'] * 100:.1f}%"   if pd.notna(row.get("unemprate_2024"))       else "N/A"
        jobs_fmt  = f"{int(row['jobs_2022']):,}"             if pd.notna(row.get("jobs_2022"))            else "N/A"

        popup_html = f"""
        <div style="font-family:sans-serif; font-size:12px; width:230px;">
          <b>{row['geoid']}</b> &mdash; <b>{row['county']}</b><br>
          <table style="border-collapse:collapse; width:100%; margin-top:4px;">
            <tr style="background:#f5f5f5"><td style="padding:2px 4px">Classification</td>
              <td style="padding:2px 4px"><b>{row['classification']}</b></td></tr>
            <tr><td style="padding:2px 4px">Rank</td>
              <td style="padding:2px 4px"><b>{row['rank']}</b></td></tr>
            <tr style="background:#f5f5f5"><td style="padding:2px 4px">Composite Score</td>
              <td style="padding:2px 4px">{row['composite_score']:.3f}</td></tr>
            <tr><td style="padding:2px 4px">Jobs (2022)</td>
              <td style="padding:2px 4px">{jobs_fmt}</td></tr>
            <tr style="background:#f5f5f5"><td style="padding:2px 4px">Poverty Rate</td>
              <td style="padding:2px 4px">{pov_pct}</td></tr>
            <tr><td style="padding:2px 4px">Median HH Income</td>
              <td style="padding:2px 4px">{inc_val}</td></tr>
            <tr style="background:#f5f5f5"><td style="padding:2px 4px">Unemployment</td>
              <td style="padding:2px 4px">{unemp_pct}</td></tr>
            <tr><td style="padding:2px 4px">Stackability</td>
              <td style="padding:2px 4px">{int(row['stackability_count'])}</td></tr>
          </table>
        </div>
        """
        folium.CircleMarker(
            location=[centroid.y, centroid.x],
            radius=6,
            color="#1a9641",
            fill=True,
            fill_color="#1a9641",
            fill_opacity=0.85,
            popup=folium.Popup(popup_html, max_width=260),
            tooltip=f"Goldilocks #{row['rank']}: {row['geoid']}",
        ).add_to(top20_layer)
    top20_layer.add_to(m)

    # ── Title overlay ─────────────────────────────────────────────────────────
    title_html = """
    <div style="
        position: fixed;
        top: 10px; left: 50px;
        z-index: 1000;
        background: white;
        padding: 8px 14px;
        border: 1px solid #ccc;
        border-radius: 4px;
        font-family: sans-serif;
        box-shadow: 2px 2px 4px rgba(0,0,0,0.2);
    ">
        <div style="font-size:14px; font-weight:bold;">
            Maryland OZ Designation &mdash; 113 Recommended Tracts
        </div>
        <div style="font-size:11px; color:#555; margin-top:3px;">
            Hover over tracts for details. Toggle layers in the panel (top right).
        </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(title_html))

    folium.LayerControl(collapsed=False).add_to(m)

    m.save(str(out_path))
    print(f"  Saved {out_path.name}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("11_visualize.py — Maryland OZ Tract Visualization")
    print("=" * 60)

    gdf = load_and_merge()

    advancing = gdf[gdf["stage1_result"] == "Advances to Scoring"].copy()
    eliminated = gdf[gdf["stage1_result"] != "Advances to Scoring"].copy()
    recommended = gdf[gdf["recommended"] == 1].copy()
    top10 = gdf[gdf["rank"] <= TOP_N_ANNOTATE].copy()
    top20_goldilocks = (
        gdf[gdf["classification"] == "Goldilocks"]
        .dropna(subset=["rank"])
        .sort_values("rank")
        .head(TOP_N_MARKERS)
        .copy()
    )
    state_boundary = gdf.dissolve()

    n_recommended  = int((gdf["recommended"] == 1).sum())
    n_gl_rec       = int(((gdf["recommended"] == 1) & (gdf["classification"] == "Goldilocks")).sum())

    print(f"\nData summary:")
    print(f"  Total tracts in merged GDF:  {len(gdf)}")
    print(f"  Advancing to scoring:        {len(advancing)}")
    print(f"  Eliminated (already attr.):  {len(eliminated)}")
    print(f"  Recommended (top {TARGET_DESIGNATIONS}):       {n_recommended}")
    print(f"  Goldilocks among recommended:{n_gl_rec}")
    print(f"  Top 20 Goldilocks for map:   {len(top20_goldilocks)}")
    score_range = advancing["composite_score"].dropna()
    print(f"  Composite score range:       {score_range.min():.3f} – {score_range.max():.3f}")

    print(f"\nProducing maps in {OUT_DIR}…")

    map_investment_heat(
        advancing, eliminated, recommended, state_boundary,
        OUT_DIR / "01_investment_heat.png",
    )
    map_community_need(
        gdf, advancing, state_boundary,
        OUT_DIR / "02_community_need.png",
    )
    map_stackability(
        gdf, state_boundary,
        OUT_DIR / "03_stackability.png",
    )
    map_composite_score(
        advancing, eliminated, recommended, top10, state_boundary,
        OUT_DIR / "04_composite_score.png",
    )

    print(f"\nBuilding interactive HTML explorer…")
    build_folium_map(
        gdf, advancing, recommended, top20_goldilocks,
        OUT_DIR / "oz_explorer.html",
    )

    print(f"\nMaps saved to {OUT_DIR}/")
    print(f"Explorer saved to {OUT_DIR / 'oz_explorer.html'}")
    print(f"Recommended tracts: {n_recommended}, Goldilocks among them: {n_gl_rec}")


if __name__ == "__main__":
    main()
