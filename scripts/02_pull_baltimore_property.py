"""
02_pull_baltimore_property.py

Pull all Baltimore City real property / SDAT parcel records from Open Baltimore's
ArcGIS Feature Service.  Paginates automatically until all records are fetched.

Output: data/raw/baltimore_real_property.csv
"""

import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "raw" / "baltimore_real_property.csv"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

BASE_URL = (
    "https://egisdata.baltimorecity.gov/egis/rest/services/"
    "Housing/dmxOwnership/MapServer/0/query"
)

# Actual field names from dmxOwnership MapServer layer 0
FIELDS = [
    "BLOCKLOT", "FULLADDR", "ZIP_CODE", "NEIGHBOR",
    "CURRLAND", "CURRIMPR", "FULLCASH",   # FULLCASH = total assessed value
    "SALEPRIC", "SALEDATE_good",          # SALEDATE_good = parsed date field
    "DHCDUSE1", "PROPDESC", "USEGROUP", "VACIND",
    "OWNER_1", "OWNMDE", "GRNDRENT",      # OWNMDE = ownership mode
]

PAGE_SIZE = 1000


def centroid_from_rings(rings: list) -> tuple[float | None, float | None]:
    """Compute a simple centroid from polygon rings (average of exterior ring vertices)."""
    if not rings:
        return None, None
    exterior = rings[0]
    if not exterior:
        return None, None
    xs = [pt[0] for pt in exterior]
    ys = [pt[1] for pt in exterior]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def fetch_page(offset: int) -> tuple[list[dict], bool]:
    params = {
        "where": "OBJECTID > 0",
        "outFields": ",".join(FIELDS),
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "json",
        "resultOffset": offset,
        "resultRecordCount": PAGE_SIZE,
        "orderByFields": "OBJECTID",
    }
    resp = requests.get(BASE_URL, params=params, timeout=90)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise RuntimeError(f"ArcGIS error: {data['error']}")

    features = data.get("features", [])
    rows = []
    for feat in features:
        row = feat.get("attributes", {})
        geom = feat.get("geometry") or {}
        # Polygon geometry -> compute centroid
        rings = geom.get("rings", [])
        x, y = centroid_from_rings(rings)
        row["X"] = x
        row["Y"] = y
        rows.append(row)
    return rows, data.get("exceededTransferLimit", False)


all_rows = []
offset = 0
page = 1

print("Fetching Baltimore real property data…")
while True:
    rows, exceeded = fetch_page(offset)
    all_rows.extend(rows)
    print(f"  Page {page:>4}: offset={offset:>7}, fetched={len(rows):>5}, total so far={len(all_rows):>7}")

    if not rows or not exceeded:
        break

    offset += PAGE_SIZE
    page += 1
    time.sleep(0.2)  # be polite to the server

df = pd.DataFrame(all_rows)
df.to_csv(OUT_PATH, index=False)
print(f"\nDone. {len(df):,} parcels saved -> {OUT_PATH}")
print(f"Columns: {list(df.columns)}")
print(f"Rows with X coordinate: {df['X'].notna().sum():,}")
