"""
03_pull_baltimore_permits.py

Pull Baltimore City building permit records from the Open Baltimore ArcGIS service.
Uses DHCD_Open_Baltimore_Datasets MapServer layer 3 (Building Permits, 278k records).

Output: data/raw/baltimore_building_permits.csv
"""

import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "raw" / "baltimore_building_permits.csv"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

BASE_URL = (
    "https://egisdata.baltimorecity.gov/egis/rest/services/"
    "Housing/DHCD_Open_Baltimore_Datasets/MapServer/3/query"
)

FIELDS = [
    "CaseNumber", "Description", "IssuedDate",
    "Address", "BLOCKLOT",
    "ExistingUse", "ProposedUse",
    "Neighborhood", "Cost",
]

PAGE_SIZE = 1000


def centroid_from_rings(rings: list) -> tuple:
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
        # Geometry might be a polygon (footprint) or a point depending on the layer
        if "x" in geom and "y" in geom:
            row["longitude"] = geom["x"]
            row["latitude"] = geom["y"]
        elif "rings" in geom:
            x, y = centroid_from_rings(geom["rings"])
            row["longitude"] = x
            row["latitude"] = y
        else:
            row["longitude"] = None
            row["latitude"] = None
        rows.append(row)
    return rows, data.get("exceededTransferLimit", False)


all_rows = []
offset = 0
page = 1

print("Fetching Baltimore building permit data...")
while True:
    rows, exceeded = fetch_page(offset)
    all_rows.extend(rows)
    print(f"  Page {page:>4}: offset={offset:>7}, fetched={len(rows):>5}, total so far={len(all_rows):>7}")

    if not rows or not exceeded:
        break

    offset += PAGE_SIZE
    page += 1
    time.sleep(0.1)

df = pd.DataFrame(all_rows)

# Normalise column names
df = df.rename(columns={
    "CaseNumber": "permit_number",
    "Description": "description",
    "IssuedDate": "issue_date",
    "Address": "address",
    "ExistingUse": "existing_use",
    "ProposedUse": "permit_type",
    "Neighborhood": "neighborhood",
    "Cost": "cost",
})

df.to_csv(OUT_PATH, index=False)
print(f"\nDone. {len(df):,} permits saved -> {OUT_PATH}")
print(f"Columns: {list(df.columns)}")
if "latitude" in df.columns:
    print(f"Rows with latitude: {df['latitude'].notna().sum():,}")
