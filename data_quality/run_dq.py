"""
data_quality/run_dq.py

Audits every stage of the OZ data pipeline for classification coverage,
geocoding quality, null prevalence, duplicates, filter logic, and scoring
data confidence.

Reads existing processed / output files — does NOT re-run the pipeline.

Outputs (all in data_quality/reports/):
  01_permits_classification.csv
  01_permits_unclassified_sample.csv
  02_property_classification.csv
  02_property_unclassified_usegroups.csv
  03_geocoding_quality.csv
  04_null_prevalence.csv
  05_deduplication.csv
  06_filter_impact.csv
  06_filter_detail.csv
  07_scoring_coverage.csv
  dq_summary.md
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parent.parent
RAW         = ROOT / "data" / "raw"
PROCESSED   = ROOT / "data" / "processed"
OUTPUT      = ROOT / "data" / "output"
REPORTS     = Path(__file__).resolve().parent / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

PERMITS_CSV   = RAW / "baltimore_building_permits.csv"
PROPERTY_CSV  = RAW / "baltimore_real_property.csv"
MASTER_CSV    = PROCESSED / "md_tracts_master.csv"
SCORED_CSV    = OUTPUT / "scored_tracts.csv"

# Store findings for the summary report
FINDINGS: dict[str, list[str]] = {}
RED_FLAGS: list[str] = []


def pct(n: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{n / total * 100:.1f}%"


def row(metric: str, value) -> dict:
    return {"metric": metric, "value": value}


def save(df: pd.DataFrame, name: str) -> None:
    path = REPORTS / name
    df.to_csv(path, index=False)
    print(f"  -> Saved {name}  ({len(df)} rows)")


def flag(message: str) -> None:
    RED_FLAGS.append(message)
    print(f"  [RED FLAG] {message}")


# ── Check A: Permit Classification Coverage ───────────────────────────────────

def check_permits() -> dict:
    print("\n=== Check A: Permit Classification ===")
    if not PERMITS_CSV.exists():
        print("  SKIP — permits CSV not found")
        return {}

    df = pd.read_csv(PERMITS_CSV, low_memory=False,
                     dtype={"geoid": str, "permit_number": str})
    total = len(df)
    print(f"  Loaded {total:,} permits")

    # Replicate exact logic from 07_aggregate_permit_stats.py
    combined = (
        df["permit_type"].fillna("") + " " + df["description"].fillna("")
    ).str.upper()

    is_new   = combined.str.contains("NEW CONSTRUCT|NEW BUILD|NEW RESIDENTIAL|NEW COMMERCIAL", regex=True, na=False)
    is_res   = combined.str.contains("RESID|HOUSING|DWELLING|SINGLE FAMILY|MULTI FAMILY",    regex=True, na=False)
    is_comm  = combined.str.contains("COMMERC|RETAIL|OFFICE|HOTEL|BUSINESS",                 regex=True, na=False)
    is_any   = is_new | is_res | is_comm
    unclass  = ~is_any

    # Date parse quality
    try:
        ts = pd.to_numeric(df["issue_date"], errors="coerce")
        parsed = pd.to_datetime(ts, unit="ms", errors="coerce")
        nat_count = int(parsed.isna().sum())
    except Exception:
        nat_count = -1

    missing_desc  = int(df["description"].isna().sum())
    missing_ptype = int(df["permit_type"].isna().sum())

    n_new   = int(is_new.sum())
    n_res   = int(is_res.sum())
    n_comm  = int(is_comm.sum())
    n_unc   = int(unclass.sum())
    n_ov_rc = int((is_res & is_comm).sum())
    n_ov_nr = int((is_new & is_res).sum())

    records = [
        row("total_permits",          total),
        row("classified_new_construction", f"{n_new} ({pct(n_new, total)})"),
        row("classified_residential",      f"{n_res} ({pct(n_res, total)})"),
        row("classified_commercial",       f"{n_comm} ({pct(n_comm, total)})"),
        row("unclassified_any",            f"{n_unc} ({pct(n_unc, total)})"),
        row("overlap_residential_and_commercial", f"{n_ov_rc} ({pct(n_ov_rc, total)})"),
        row("overlap_new_construction_and_residential", f"{n_ov_nr} ({pct(n_ov_nr, total)})"),
        row("missing_description",    f"{missing_desc} ({pct(missing_desc, total)})"),
        row("missing_permit_type",    f"{missing_ptype} ({pct(missing_ptype, total)})"),
        row("date_parse_failures_nat", f"{nat_count} ({pct(nat_count, total)})" if nat_count >= 0 else "error"),
    ]
    save(pd.DataFrame(records), "01_permits_classification.csv")

    # Sample of unclassified descriptions
    unc_sample = (
        df[unclass][["permit_number", "permit_type", "description", "neighborhood"]]
        .dropna(subset=["description"])
        .sample(min(30, int(unclass.sum())), random_state=42)
        if int(unclass.sum()) > 0 else pd.DataFrame()
    )
    save(unc_sample, "01_permits_unclassified_sample.csv")

    if n_unc / total > 0.25:
        flag(f"Check A: {pct(n_unc, total)} of permits unclassified into any category ({n_unc:,} of {total:,})")

    return {
        "total": total,
        "new": n_new, "res": n_res, "comm": n_comm,
        "unclassified": n_unc, "overlap_rc": n_ov_rc,
        "missing_desc": missing_desc, "date_failures": nat_count,
    }


# ── Check B: Property Classification Coverage ─────────────────────────────────

def check_property() -> dict:
    print("\n=== Check B: Property Classification ===")
    if not PROPERTY_CSV.exists():
        print("  SKIP — property CSV not found")
        return {}

    df = pd.read_csv(PROPERTY_CSV, low_memory=False, dtype={"geoid": str})
    total = len(df)
    print(f"  Loaded {total:,} parcels")

    # Use group classification — exact logic from 06_aggregate_property_stats.py
    ug = df["USEGROUP"].fillna("").str.strip().str.upper()
    pd_col = df["PROPDESC"].fillna("").str.upper()

    is_res  = ug.str.startswith("R") | pd_col.str.contains("RESID", na=False)
    is_comm = ug.str.startswith("C") | pd_col.str.contains("COMMERC|RETAIL|OFFICE|HOTEL", regex=True, na=False)
    is_ind  = ug.str.startswith("I") | pd_col.str.contains("INDUSTR|MANUFACTUR|WAREHOUSE|STORAGE", regex=True, na=False)
    is_any  = is_res | is_comm | is_ind
    unclass = ~is_any

    # Compound / non-single-letter USEGROUP codes (e.g. "EC", "CR", "RC")
    compound_mask = ug.str.len() >= 2
    compound_vals = ug[compound_mask & unclass].value_counts()

    # Vacancy flags
    vacind_col = df["VACIND"].fillna("").str.strip().str.upper()
    is_vac_flag  = vacind_col == "Y"
    is_vac_zero  = pd.to_numeric(df["CURRIMPR"], errors="coerce").fillna(-1) == 0
    is_vac_either = is_vac_flag | is_vac_zero

    # VACIND value distribution
    vacind_dist = df["VACIND"].fillna("__null__").str.strip().value_counts().to_dict()

    # Owner-occupancy — CRITICAL: check actual values vs. expected "Y"/"H"
    ownmde_col = df["OWNMDE"].fillna("__null__").str.strip().str.upper()
    ownmde_dist = ownmde_col.value_counts().to_dict()
    is_owner = ownmde_col.isin(["Y", "H"])

    # Financial quality
    fullcash     = pd.to_numeric(df["FULLCASH"], errors="coerce").fillna(0)
    salepric     = pd.to_numeric(df["SALEPRIC"], errors="coerce").fillna(0)
    zero_cash    = int((fullcash <= 0).sum())
    zero_sale    = int((salepric <= 0).sum())

    missing_ug   = int(df["USEGROUP"].isna().sum())
    missing_pd   = int(df["PROPDESC"].isna().sum())

    n_res   = int(is_res.sum())
    n_comm  = int(is_comm.sum())
    n_ind   = int(is_ind.sum())
    n_unc   = int(unclass.sum())
    n_ov_rc = int((is_res & is_comm).sum())

    records = [
        row("total_parcels",           total),
        row("classified_residential",  f"{n_res} ({pct(n_res, total)})"),
        row("classified_commercial",   f"{n_comm} ({pct(n_comm, total)})"),
        row("classified_industrial",   f"{n_ind} ({pct(n_ind, total)})"),
        row("unclassified_use",        f"{n_unc} ({pct(n_unc, total)})"),
        row("overlap_res_and_comm",    f"{n_ov_rc} ({pct(n_ov_rc, total)})"),
        row("flagged_vacant_by_vacind",  f"{int(is_vac_flag.sum())} ({pct(int(is_vac_flag.sum()), total)})"),
        row("flagged_vacant_by_zeroimpr",f"{int(is_vac_zero.sum())} ({pct(int(is_vac_zero.sum()), total)})"),
        row("flagged_vacant_either",     f"{int(is_vac_either.sum())} ({pct(int(is_vac_either.sum()), total)})"),
        row("vacind_Y",   vacind_dist.get("Y", 0)),
        row("vacind_N",   vacind_dist.get("N", 0)),
        row("vacind_null",vacind_dist.get("__null__", 0)),
        row("vacind_other_values", str({k: v for k, v in vacind_dist.items() if k not in ("Y", "N", "__null__")})),
        row("ownmde_Y",   ownmde_dist.get("Y", 0)),
        row("ownmde_H",   ownmde_dist.get("H", 0)),
        row("ownmde_null",ownmde_dist.get("__NULL__", 0)),
        row("ownmde_other_values", str({k: v for k, v in ownmde_dist.items() if k not in ("Y", "H", "__NULL__")})),
        row("parcels_classified_owner_occ", f"{int(is_owner.sum())} ({pct(int(is_owner.sum()), total)}) — NOTE: script expects Y/H"),
        row("zero_or_negative_fullcash",    f"{zero_cash} ({pct(zero_cash, total)})"),
        row("zero_or_negative_salepric",    f"{zero_sale} ({pct(zero_sale, total)})"),
        row("missing_usegroup",  f"{missing_ug} ({pct(missing_ug, total)})"),
        row("missing_propdesc",  f"{missing_pd} ({pct(missing_pd, total)})"),
    ]
    save(pd.DataFrame(records), "02_property_classification.csv")

    # Top unclassified USEGROUP values
    unc_df = pd.DataFrame(
        compound_vals.head(20).reset_index()
    )
    unc_df.columns = ["usegroup_value", "parcel_count"]
    save(unc_df, "02_property_unclassified_usegroups.csv")

    # Red flags
    if n_unc / total > 0.10:
        flag(f"Check B: {pct(n_unc, total)} of parcels unclassified into residential/commercial/industrial ({n_unc:,})")
    if int(is_owner.sum()) == 0:
        flag("Check B: OWNMDE column contains NO 'Y' or 'H' values — owner-occupancy rate is effectively 0 for all tracts (script 06 assumes Y/H but actual values differ)")

    return {
        "total": total,
        "res": n_res, "comm": n_comm, "ind": n_ind,
        "unclassified": n_unc,
        "vac_flag": int(is_vac_flag.sum()), "vac_zero": int(is_vac_zero.sum()),
        "owner_occ": int(is_owner.sum()),
        "zero_cash": zero_cash,
    }


# ── Check C: Geocoding / Spatial Join Quality ─────────────────────────────────

def check_geocoding() -> dict:
    print("\n=== Check C: Geocoding Quality ===")
    results = []

    for label, csv_path, coord_cols in [
        ("parcels", PROPERTY_CSV, ("X", "Y")),
        ("permits", PERMITS_CSV,  ("longitude", "latitude")),
    ]:
        if not csv_path.exists():
            print(f"  SKIP {label} — file not found")
            continue

        df = pd.read_csv(csv_path, low_memory=False, dtype={"geoid": str})
        total = len(df)
        cx, cy = coord_cols

        # Missing coords
        x_num = pd.to_numeric(df[cx], errors="coerce") if cx in df.columns else pd.Series(dtype=float)
        y_num = pd.to_numeric(df[cy], errors="coerce") if cy in df.columns else pd.Series(dtype=float)
        missing_coord = int((x_num.isna() | y_num.isna()).sum())
        non_numeric   = int(missing_coord)  # pd.to_numeric coerces non-numeric to NaN

        # Geoid match quality
        geoid_col = df["geoid"] if "geoid" in df.columns else pd.Series(dtype=str)
        matched   = int(geoid_col.notna().sum())
        unmatched = total - matched

        # Tract distribution
        if matched > 0:
            tract_counts = geoid_col.dropna().value_counts()
            unique_tracts    = int(tract_counts.nunique()) if len(tract_counts) else 0
            zero_rec_tracts  = max(0, 199 - unique_tracts)
            dist_min  = int(tract_counts.min())  if len(tract_counts) else 0
            dist_p25  = int(tract_counts.quantile(0.25))
            dist_med  = int(tract_counts.median())
            dist_p75  = int(tract_counts.quantile(0.75))
            dist_max  = int(tract_counts.max())
        else:
            unique_tracts = zero_rec_tracts = 0
            dist_min = dist_p25 = dist_med = dist_p75 = dist_max = 0

        results.append({
            "dataset":               label,
            "total_records":         total,
            "missing_coord":         f"{missing_coord} ({pct(missing_coord, total)})",
            "matched_geoid_not_null":f"{matched} ({pct(matched, total)})",
            "unmatched_null_geoid":  f"{unmatched} ({pct(unmatched, total)})",
            "unique_tracts_matched": unique_tracts,
            "expected_baltimore_tracts": 199,
            "tracts_with_zero_records":  zero_rec_tracts,
            "min_records_per_tract":  dist_min,
            "p25_records_per_tract":  dist_p25,
            "median_records_per_tract": dist_med,
            "p75_records_per_tract":  dist_p75,
            "max_records_per_tract":  dist_max,
        })

        match_rate = matched / total if total else 0
        if match_rate < 0.95:
            flag(f"Check C: {label} geocoding match rate is {pct(matched, total)} (below 95% threshold)")

    save(pd.DataFrame(results), "03_geocoding_quality.csv")
    return {"datasets": [r["dataset"] for r in results]}


# ── Check D: Null / Missing Value Prevalence ──────────────────────────────────

# Columns expected to be NaN for non-Baltimore tracts (by design)
BY_DESIGN_COLS = {
    "total_parcels", "land_to_value_ratio", "vacancy_proxy", "market_activity_count",
    "median_sale_price", "owner_occupancy_rate", "pct_residential", "pct_commercial",
    "pct_industrial", "assessed_value_per_parcel",
    "permits_total", "permits_new_construction", "permits_residential",
    "permits_commercial", "permit_trend",
}

# Scoring inputs and their weights
SCORING_COLS = {
    "jobs_2022": 0.30,
    "land_to_value_ratio": 0.06,
    "vacancy_proxy": 0.06,
    "permit_trend": 0.05,
    "median_sale_price": 0.05,
    "povrate_2024": 0.15,
    "median_hhincome_2024": 0.10,
    "unemprate_2024": 0.08,
    "stackability_count": 0.15,
}


def check_nulls() -> dict:
    print("\n=== Check D: Null / Missing Value Prevalence ===")
    tables = {
        "md_tracts_base":                PROCESSED / "md_tracts_base.csv",
        "baltimore_tract_property_stats": PROCESSED / "baltimore_tract_property_stats.csv",
        "baltimore_tract_permit_stats":   PROCESSED / "baltimore_tract_permit_stats.csv",
        "md_tracts_master":              MASTER_CSV,
        "scored_tracts":                 SCORED_CSV,
    }

    all_rows = []
    high_null_scoring = []

    for table_name, path in tables.items():
        if not path.exists():
            print(f"  SKIP {table_name} — file not found")
            continue
        df = pd.read_csv(path, low_memory=False, dtype={"geoid": str})
        total_rows = len(df)
        print(f"  {table_name}: {total_rows} rows, {len(df.columns)} cols")

        # For master table, compute null rates on Baltimore tracts only for by-design cols
        balt_mask = None
        if table_name == "md_tracts_master" and "geoid" in df.columns:
            balt_mask = df["geoid"].str.startswith("24510", na=False)

        for col in df.columns:
            null_count = int(df[col].isna().sum())
            null_rate  = null_count / total_rows if total_rows else 0

            # For by-design columns in master, also compute null rate within Baltimore
            by_design_note = ""
            if col in BY_DESIGN_COLS and balt_mask is not None:
                balt_null = int(df.loc[balt_mask, col].isna().sum())
                balt_total = int(balt_mask.sum())
                by_design_note = f"within_baltimore_nulls={balt_null}/{balt_total}"

            if col in BY_DESIGN_COLS:
                flag_val = "by_design (NaN for non-Baltimore tracts)"
                if by_design_note:
                    flag_val += f" | {by_design_note}"
            elif col == "composite_score" and table_name == "scored_tracts":
                flag_val = "ok (NaN for eliminated tracts)"
            elif null_rate > 0.5:
                flag_val = "HIGH NULL RATE"
            elif null_rate > 0.1:
                flag_val = "moderate null rate"
            else:
                flag_val = "ok"

            # Extra attention to scoring cols in master/scored
            if col in SCORING_COLS and table_name in ("md_tracts_master", "scored_tracts"):
                if null_rate > 0.05:
                    high_null_scoring.append((table_name, col, null_count, null_rate))

            all_rows.append({
                "table":      table_name,
                "column":     col,
                "null_count": null_count,
                "null_rate":  f"{null_rate*100:.1f}%",
                "flag":       flag_val,
            })

    save(pd.DataFrame(all_rows), "04_null_prevalence.csv")

    for table_name, col, nc, nr in high_null_scoring:
        weight = SCORING_COLS.get(col, 0)
        flag(f"Check D: '{col}' has {nr*100:.1f}% nulls in {table_name} (scoring weight {weight*100:.0f}%) — {nc} tracts will use imputed defaults")

    return {"high_null_scoring": high_null_scoring}


# ── Check E: Deduplication ────────────────────────────────────────────────────

def check_deduplication() -> dict:
    print("\n=== Check E: Deduplication ===")
    records = []

    # Parcels — BLOCKLOT
    if PROPERTY_CSV.exists():
        df = pd.read_csv(PROPERTY_CSV, usecols=["BLOCKLOT", "FULLADDR", "FULLCASH"],
                         low_memory=False)
        total = len(df)
        dup_blocklot = int(df.duplicated(subset=["BLOCKLOT"]).sum())
        records.append({
            "dataset":       "parcels",
            "duplicate_key": "BLOCKLOT",
            "total_rows":    total,
            "duplicate_rows":dup_blocklot,
            "pct":           pct(dup_blocklot, total),
        })
        if dup_blocklot > 0:
            flag(f"Check E: {dup_blocklot:,} duplicate BLOCKLOTs in parcel data ({pct(dup_blocklot, total)})")

    # Permits — permit_number
    if PERMITS_CSV.exists():
        df = pd.read_csv(PERMITS_CSV, usecols=["permit_number", "address", "description", "issue_date"],
                         low_memory=False, dtype={"permit_number": str})
        total = len(df)

        dup_permit = int(df.duplicated(subset=["permit_number"]).sum())
        records.append({
            "dataset":       "permits",
            "duplicate_key": "permit_number",
            "total_rows":    total,
            "duplicate_rows":dup_permit,
            "pct":           pct(dup_permit, total),
        })

        dup_combo = int(df.dropna(subset=["address", "description", "issue_date"])
                          .duplicated(subset=["address", "description", "issue_date"]).sum())
        records.append({
            "dataset":       "permits",
            "duplicate_key": "address + description + issue_date",
            "total_rows":    total,
            "duplicate_rows":dup_combo,
            "pct":           pct(dup_combo, total),
        })

        if dup_permit > 0:
            flag(f"Check E: {dup_permit:,} duplicate permit_numbers ({pct(dup_permit, total)})")
        if dup_combo / total > 0.01:
            flag(f"Check E: {dup_combo:,} permits with duplicate address+description+date ({pct(dup_combo, total)})")

    save(pd.DataFrame(records), "05_deduplication.csv")
    return {"records": records}


# ── Check F: Filter Impact Analysis ──────────────────────────────────────────

def check_filter_impact() -> dict:
    print("\n=== Check F: Filter Impact Analysis ===")
    if not SCORED_CSV.exists():
        print("  SKIP — scored_tracts.csv not found")
        return {}

    df = pd.read_csv(SCORED_CSV, dtype={"geoid": str}, low_memory=False)

    required_cols = {"stage1_result", "jobs_2022", "povrate_2024",
                     "has_any_permits", "median_hhincome_2024", "median_homevalue_2024"}
    if not required_cols.issubset(df.columns):
        print(f"  SKIP — scored_tracts.csv missing expected columns. Found: {list(df.columns[:5])}...")
        return {}

    total = len(df)
    advances = df[df["stage1_result"] == "Advances to Scoring"]
    el_attr  = df[df["stage1_result"] == "Eliminated — Already Attractive"]
    el_unv   = df[df["stage1_result"] == "Eliminated — Unviable"]

    # Tracts eliminated as unviable that are NOT in Baltimore (no permit data)
    unv_non_balt = el_unv[~el_unv["geoid"].str.startswith("24510", na=False)]
    unv_zero_jobs = el_unv[pd.to_numeric(el_unv["jobs_2022"], errors="coerce").fillna(-1) == 0]
    unv_nan_jobs  = el_unv[pd.to_numeric(el_unv["jobs_2022"], errors="coerce").isna()]

    # Thresholds used by filter (recompute from data)
    metro_median = float(pd.to_numeric(df["median_hhincome_2024"], errors="coerce").median())
    top_quartile = float(pd.to_numeric(df["median_homevalue_2024"], errors="coerce").quantile(0.75))

    records = [
        row("total_tracts",            total),
        row("advances_to_scoring",     len(advances)),
        row("eliminated_already_attractive", len(el_attr)),
        row("eliminated_unviable",     len(el_unv)),
        row("unviable_non_baltimore",  f"{len(unv_non_balt)} — eliminated with no Baltimore permit data"),
        row("unviable_actual_zero_jobs", len(unv_zero_jobs)),
        row("unviable_jobs_nan",       len(unv_nan_jobs)),
        row("metro_median_income_used",f"${metro_median:,.0f}"),
        row("top_quartile_homevalue_used", f"${top_quartile:,.0f}"),
        row("check_sum_valid",         str(len(advances) + len(el_attr) + len(el_unv) == total)),
    ]
    save(pd.DataFrame(records), "06_filter_impact.csv")

    # Full detail file
    detail_cols = ["geoid", "county", "classification", "stage1_result",
                   "jobs_2022", "povrate_2024", "has_any_permits",
                   "median_hhincome_2024", "median_homevalue_2024"]
    detail_cols = [c for c in detail_cols if c in df.columns]
    save(df[detail_cols].sort_values("stage1_result"), "06_filter_detail.csv")

    if len(unv_non_balt) > 0:
        flag(f"Check F: {len(unv_non_balt)} tracts eliminated as 'Unviable' are outside Baltimore — their has_any_permits=0 is a data-absence default, not evidence of no construction")

    return {
        "total": total,
        "advances": len(advances),
        "el_attr": len(el_attr),
        "el_unv": len(el_unv),
        "unv_non_balt": len(unv_non_balt),
        "metro_median": metro_median,
        "top_quartile": top_quartile,
    }


# ── Check G: Scoring Data Coverage ────────────────────────────────────────────

def check_scoring_coverage() -> dict:
    print("\n=== Check G: Scoring Data Coverage ===")
    if not SCORED_CSV.exists() or not MASTER_CSV.exists():
        print("  SKIP — scored_tracts.csv or master CSV not found")
        return {}

    scored = pd.read_csv(SCORED_CSV, dtype={"geoid": str}, low_memory=False)
    master = pd.read_csv(MASTER_CSV, dtype={"geoid": str}, low_memory=False)

    if "recommended" not in scored.columns:
        print("  SKIP — 'recommended' column not in scored_tracts.csv")
        return {}

    # Work with recommended tracts
    rec = scored[scored["recommended"] == 1].copy()
    n_rec = len(rec)
    print(f"  {n_rec} recommended tracts")

    # Join master for pre-scoring NaN status
    master_slim = master[["geoid"] + [c for c in SCORING_COLS if c in master.columns]].copy()
    rec_m = rec.merge(master_slim, on="geoid", how="left", suffixes=("", "_master"))

    summary_rows = []
    per_tract_rows = []

    for col, weight in SCORING_COLS.items():
        master_col = col + "_master" if col + "_master" in rec_m.columns else col
        if master_col not in rec_m.columns and col not in rec_m.columns:
            continue
        src_col = master_col if master_col in rec_m.columns else col
        vals = pd.to_numeric(rec_m[src_col], errors="coerce")
        n_real    = int(vals.notna().sum())
        n_imputed = int(vals.isna().sum())
        summary_rows.append({
            "scoring_input": col,
            "weight_pct":    f"{weight*100:.0f}%",
            "n_recommended": n_rec,
            "n_real_data":   n_real,
            "n_imputed":     n_imputed,
            "pct_imputed":   pct(n_imputed, n_rec),
        })
        if n_imputed / n_rec > 0.20:
            flag(f"Check G: '{col}' ({weight*100:.0f}% weight) is imputed for {pct(n_imputed, n_rec)} of recommended tracts ({n_imputed}/{n_rec})")

    save(pd.DataFrame(summary_rows), "07_scoring_coverage_summary.csv")

    # Per-tract data confidence
    for _, row_data in rec_m.iterrows():
        weight_real = 0.0
        for col, weight in SCORING_COLS.items():
            src = col + "_master" if col + "_master" in rec_m.columns else col
            val = pd.to_numeric(row_data.get(src, float("nan")), errors="coerce")
            if pd.notna(val):
                weight_real += weight
        per_tract_rows.append({
            "geoid":              row_data.get("geoid"),
            "county":             row_data.get("county"),
            "classification":     row_data.get("classification"),
            "rank":               row_data.get("rank"),
            "composite_score":    row_data.get("composite_score"),
            "data_confidence_pct":f"{weight_real*100:.1f}%",
            "low_confidence":     weight_real < 0.60,
        })

    pt_df = pd.DataFrame(per_tract_rows).sort_values("rank")
    save(pt_df, "07_scoring_coverage.csv")

    n_low = int(pt_df["low_confidence"].sum())
    if n_low > 0:
        flag(f"Check G: {n_low} recommended tracts have <60% of their composite score weight backed by real data")

    return {"n_recommended": n_rec, "n_low_confidence": n_low, "summary": summary_rows}


# ── Summary Report ────────────────────────────────────────────────────────────

def write_summary(a: dict, b: dict, c: dict, d: dict, e: dict, f: dict, g: dict) -> None:
    print("\n=== Writing dq_summary.md ===")

    def fmt(d: dict, key: str, default="N/A"):
        val = d.get(key, default)
        if isinstance(val, int):
            return f"{val:,}"
        return str(val)

    red_flag_block = "\n".join(f"- {r}" for r in RED_FLAGS) if RED_FLAGS else "None identified."

    scoring_table = ""
    if g.get("summary"):
        scoring_table = "| Scoring Input | Weight | Imputed (of 113) | % Imputed |\n"
        scoring_table += "|---|---|---|---|\n"
        for s in g["summary"]:
            scoring_table += f"| {s['scoring_input']} | {s['weight_pct']} | {s['n_imputed']} | {s['pct_imputed']} |\n"

    content = textwrap.dedent(f"""\
    # OZ Pipeline — Data Quality Report

    *Generated by `data_quality/run_dq.py`*

    ---

    ## Red Flags

    {red_flag_block}

    ---

    ## Check A: Permit Classification Coverage

    **Source:** `data/raw/baltimore_building_permits.csv`
    **Mirrors logic in:** `scripts/07_aggregate_permit_stats.py`

    | Metric | Value |
    |---|---|
    | Total permits | {fmt(a, "total")} |
    | Classified: new construction | {fmt(a, "new")} |
    | Classified: residential | {fmt(a, "res")} |
    | Classified: commercial | {fmt(a, "comm")} |
    | **Unclassified (none of 3)** | **{fmt(a, "unclassified")}** |
    | Overlap res + commercial | {fmt(a, "overlap_rc")} |
    | Missing description field | {fmt(a, "missing_desc")} |
    | Date parse failures | {fmt(a, "date_failures")} |

    See `reports/01_permits_classification.csv` and `01_permits_unclassified_sample.csv`.

    ---

    ## Check B: Property Classification Coverage

    **Source:** `data/raw/baltimore_real_property.csv`
    **Mirrors logic in:** `scripts/06_aggregate_property_stats.py`

    | Metric | Value |
    |---|---|
    | Total parcels | {fmt(b, "total")} |
    | Classified: residential | {fmt(b, "res")} |
    | Classified: commercial | {fmt(b, "comm")} |
    | Classified: industrial | {fmt(b, "ind")} |
    | **Unclassified (none of 3)** | **{fmt(b, "unclassified")}** |
    | Flagged vacant (VACIND=Y) | {fmt(b, "vac_flag")} |
    | Flagged vacant (CURRIMPR=0) | {fmt(b, "vac_zero")} |
    | Owner-occupied (OWNMDE=Y/H) | {fmt(b, "owner_occ")} |
    | Parcels with zero FULLCASH | {fmt(b, "zero_cash")} |

    > **Note:** OWNMDE actual values in the raw data may differ from the "Y"/"H" values expected by script 06.
    > Check `02_property_classification.csv` for the `ownmde_other_values` row.

    See `reports/02_property_classification.csv` and `02_property_unclassified_usegroups.csv`.

    ---

    ## Check C: Geocoding / Spatial Join Quality

    **Sources:** Both raw CSVs, geoid column added by `scripts/05_geocode_to_tracts.py`

    See `reports/03_geocoding_quality.csv`.

    ---

    ## Check D: Null / Missing Value Prevalence

    **Sources:** All 5 processed/output tables

    Key scoring columns with elevated null rates (>5% in master table):

    {chr(10).join("- " + f"{t} / {c}: {nc} nulls ({nr*100:.1f}%)" for t, c, nc, nr in d.get("high_null_scoring", [])) or "- None above 5% threshold"}

    See `reports/04_null_prevalence.csv` for full per-column breakdown.

    ---

    ## Check E: Deduplication

    See `reports/05_deduplication.csv`.

    ---

    ## Check F: Filter Impact Analysis

    **Source:** `data/output/scored_tracts.csv`

    | Metric | Value |
    |---|---|
    | Total tracts | {fmt(f, "total")} |
    | Advances to scoring | {fmt(f, "advances")} |
    | Eliminated — Already Attractive | {fmt(f, "el_attr")} |
    | Eliminated — Unviable | {fmt(f, "el_unv")} |
    | Unviable (non-Baltimore, no permit data) | {fmt(f, "unv_non_balt")} |
    | Metro median income threshold | {f.get("metro_median", "N/A") if not f.get("metro_median") or isinstance(f.get("metro_median"), str) else f"${f['metro_median']:,.0f}"} |
    | Top quartile home value threshold | {f.get("top_quartile", "N/A") if not f.get("top_quartile") or isinstance(f.get("top_quartile"), str) else f"${f['top_quartile']:,.0f}"} |

    See `reports/06_filter_impact.csv` and `06_filter_detail.csv`.

    ---

    ## Check G: Scoring Data Coverage (113 Recommended Tracts)

    {scoring_table if scoring_table else "No data available."}

    Tracts with <60% data confidence: **{fmt(g, "n_low_confidence")}**

    See `reports/07_scoring_coverage.csv` for per-tract breakdown.
    """)

    path = REPORTS / "dq_summary.md"
    path.write_text(content, encoding="utf-8")
    print(f"  -> Saved dq_summary.md")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("OZ Pipeline — Data Quality Audit")
    print("=" * 60)

    a = check_permits()
    b = check_property()
    c = check_geocoding()
    d = check_nulls()
    e = check_deduplication()
    f = check_filter_impact()
    g = check_scoring_coverage()

    write_summary(a, b, c, d, e, f, g)

    print("\n" + "=" * 60)
    print(f"Done. Reports in: {REPORTS}")
    print(f"Red flags found: {len(RED_FLAGS)}")
    for rf in RED_FLAGS:
        print(f"  * {rf}")
    print("=" * 60)


if __name__ == "__main__":
    main()
