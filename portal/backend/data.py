"""Data access: BigQuery -> compact JSON snapshots in data/.

The map needs every cell at once (~30k rows), so it is served from a snapshot rather than
queried per request. Refresh the snapshot after rebuilding a4i_grid:

    python -m backend.data refresh
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from functools import lru_cache

from . import config

CELLS_FILE = config.CACHE_DIR / "cells.json"
TRACTS_FILE = config.CACHE_DIR / "tracts.geojson"
HEATDAYS_FILE = config.CACHE_DIR / "heat_days.json"

# Columns exported per cell from a4i_grid.cell_profile, in order. Keys and bookkeeping
# first, then the heat, built-environment and impact layers the map can colour by.
CELL_COLUMNS = [
    # keys / bookkeeping (cells)
    "cell_i", "cell_j", "tract_geo_id", "bg_geo_id", "borough",
    "is_driven", "dist_to_driven_m", "in_training_range", "is_land",
    # heat: measured (cell_heat) and estimated history (cell_heat_summary)
    "offset_f", "heat_index_offset_f", "n_readings", "holdout",
    "est_days_ge_90_per_year", "est_days_ge_95_per_year", "est_days_ge_100_per_year",
    "est_peak_f", "trend_days_ge_95_per_year",
    # built environment = model features (cell_built)
    "trees_50m", "trees_100m", "trees_250m", "tree_dbh_sum_100m",
    "dist_open_space_m", "tract_water_share", "bg_housing_units_per_km2",
    # impact = who lives here, never model inputs (cell_impact)
    "bg_total_pop", "bg_share_65_plus", "bg_median_age", "bg_median_income",
    "bg_renter_share", "bg_severe_rent_burden_rate", "bg_pop_per_km2",
    "tract_no_vehicle_rate", "tract_poverty_rate",
    "est_residents", "est_residents_65_plus", "est_households_no_car",
]

TRACT_COLUMNS = [
    "geo_id", "borough", "tract_name", "total_pop", "pop_65_plus", "share_65_plus",
    "median_age", "median_income", "income_per_capita", "poverty_rate", "households",
    "no_cars", "no_vehicle_rate", "housing_units_per_km2", "pop_per_km2", "water_share",
]


def _client():
    from google.cloud import bigquery

    if config.ON_CLOUD_RUN:
        return bigquery.Client(project=config.PROJECT_ID)

    import google.oauth2.credentials

    token = subprocess.run(
        ["gcloud", "auth", "print-access-token"], check=True, capture_output=True, text=True
    ).stdout.strip()
    creds = google.oauth2.credentials.Credentials(token)
    return bigquery.Client(project=config.PROJECT_ID, credentials=creds)


def _clean(v):
    """JSON-safe scalar: NaN -> None, floats rounded to keep the payload small."""
    if v is None:
        return None
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return round(v, 4)
    return v


def _query(sql: str):
    return list(_client().query(sql).result())


def refresh() -> None:
    """Pull the grid, tracts and station history from BigQuery into data/."""
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    g = f"`{config.PROJECT_ID}.{config.GRID_DATASET}`"

    rows = _query(f"SELECT {', '.join(CELL_COLUMNS)} FROM {g}.cell_profile")
    cells = {
        "cell_deg": config.CELL_DEG,
        "columns": CELL_COLUMNS,
        "rows": [[_clean(r[c]) for c in CELL_COLUMNS] for r in rows],
    }
    CELLS_FILE.write_text(json.dumps(cells, separators=(",", ":")))
    print(f"cells: {len(rows):,} -> {CELLS_FILE}")

    # Tracts the grid touches, geometry simplified to ~10 m for the browser.
    rows = _query(f"""
        SELECT {", ".join(TRACT_COLUMNS)},
               ST_ASGEOJSON(ST_SIMPLIFY(tract_geom, 10)) AS geom
        FROM {g}.tract_exposure
        WHERE geo_id IN (SELECT DISTINCT tract_geo_id FROM {g}.cells WHERE tract_geo_id IS NOT NULL)
    """)
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": json.loads(r["geom"]),
             "properties": {c: _clean(r[c]) for c in TRACT_COLUMNS}}
            for r in rows
        ],
    }
    TRACTS_FILE.write_text(json.dumps(fc, separators=(",", ":")))
    print(f"tracts: {len(rows):,} -> {TRACTS_FILE}")

    # Days per year over heat thresholds, city-wide reference (see sql/grid/05).
    rows = _query(f"""
        SELECT year, days_ge_90 AS days_90, days_ge_95 AS days_95,
               days_ge_100 AS days_100, peak_f
        FROM {g}.city_heat_history
        ORDER BY year
    """)
    HEATDAYS_FILE.write_text(json.dumps(
        {"station": "City reference: average daily high of Central Park, LaGuardia and JFK",
         "years": [{k: _clean(r[k]) for k in ("year", "days_90", "days_95", "days_100", "peak_f")}
                   for r in rows]}, separators=(",", ":")))
    print(f"heat days: {len(rows)} years -> {HEATDAYS_FILE}")


@lru_cache(maxsize=None)
def _load(path) -> str:
    if not path.exists() and config.ON_CLOUD_RUN:
        refresh()  # first request on a fresh container builds the snapshot
    if not path.exists():
        raise FileNotFoundError(
            f"{path.name} not found. Build the snapshot first: python -m backend.data refresh")
    return path.read_text()


def cells_json() -> str:
    return _load(CELLS_FILE)


def tracts_json() -> str:
    return _load(TRACTS_FILE)


def heat_days_json() -> str:
    return _load(HEATDAYS_FILE)


if __name__ == "__main__":
    if sys.argv[1:] == ["refresh"]:
        refresh()
    else:
        print(__doc__)
