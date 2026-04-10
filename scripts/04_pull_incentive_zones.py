"""
04_pull_incentive_zones.py

Pull Maryland incentive zone polygons from MD iMAP ArcGIS REST service.
Fetches Enterprise Zones (layer 4), Sustainable Communities (layer 6),
and RISE Zones (layer 11).

Outputs:
  data/raw/imap_incentive_zones/enterprise_zones.geojson
  data/raw/imap_incentive_zones/sustainable_communities.geojson
  data/raw/imap_incentive_zones/rise_zones.geojson
"""

import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "raw" / "imap_incentive_zones"
OUT_DIR.mkdir(parents=True, exist_ok=True)

IMAP_BASE = (
    "https://mdgeodata.md.gov/imap/rest/services/BusinessEconomy/"
    "MD_IncentiveZones/MapServer"
)

LAYERS = {
    4:  "enterprise_zones",
    6:  "sustainable_communities",
    11: "rise_zones",
}


def fetch_layer_geojson(layer_id: int, name: str) -> dict | None:
    """Query one iMAP layer and return a GeoJSON FeatureCollection."""
    url = f"{IMAP_BASE}/{layer_id}/query"
    params = {
        "where": "1=1",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
        "resultOffset": 0,
        "resultRecordCount": 2000,
    }

    print(f"Fetching layer {layer_id} ({name}) …")
    try:
        resp = requests.get(url, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return None

    features = data.get("features", [])
    print(f"  Got {len(features)} features")

    # Wrap in standard FeatureCollection if not already
    if data.get("type") != "FeatureCollection":
        data = {"type": "FeatureCollection", "features": features}
    return data


for layer_id, name in LAYERS.items():
    out_file = OUT_DIR / f"{name}.geojson"
    geojson = fetch_layer_geojson(layer_id, name)

    if geojson is None:
        print(f"  Saving empty placeholder for {name}")
        geojson = {"type": "FeatureCollection", "features": []}

    out_file.write_text(json.dumps(geojson, indent=2))
    print(f"  Saved -> {out_file}\n")
    time.sleep(0.5)

print("Done — incentive zone layers downloaded.")
