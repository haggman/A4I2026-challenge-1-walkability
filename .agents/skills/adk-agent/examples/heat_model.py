"""Tools that call the BigQuery ML offset model. The required "tool you built"."""
from __future__ import annotations

import logging
import math

from google.adk.tools import ToolContext

from ..bq import load_sql, run
from ..config import settings
from ..schemas import Driver, HeatExplanation

log = logging.getLogger(__name__)

# Model feature → words a planner uses. Keep in sync with the data lane's feature list.
FEATURE_LABELS = {
    "km_from_center": "distance from the urban core",
    "median_year_built": "age of the housing stock",
    "pop_density_km2": "population density",
    "housing_density_km2": "housing density",
    "water_share": "nearby water",
    "pop_within_1500m": "people living within 1.5 km",
    "housing_within_1500m": "homes within 1.5 km",
    "mean_year_built_1500m": "age of surrounding buildings",
}


def _drivers(raw: list[dict]) -> list[Driver]:
    return [
        Driver(feature=d["feature"],
               label=FEATURE_LABELS.get(d["feature"], d["feature"].replace("_", " ")),
               attribution_f=round(float(d["attribution_f"]), 1))
        for d in raw
    ]


def explain_heat_offset(lat: float, lon: float, forecast_high_f: float = 0.0,
                        tool_context: ToolContext | None = None) -> dict:
    """Predicts how much hotter or cooler a location runs than the city average, and why.

    Calls the team's BigQuery ML model with ML.EXPLAIN_PREDICT. Works for locations that were
    never measured. Use this whenever the planner asks how hot a place is, why one place is
    hotter than another, or to compare candidate sites.

    Args:
        lat: Latitude in decimal degrees (WGS84).
        lon: Longitude in decimal degrees (WGS84).
        forecast_high_f: Optional city-wide forecast high in °F. If given (>0), the result also
            includes an implied local high = forecast + offset, labelled as an estimate.

    Returns:
        dict with status, predicted_offset_f (°F vs. city average), drivers (per-feature °F
        contributions), implied_local_high_f, and a one-sentence summary. status is
        "out_of_scope" if the point is outside the area the heat campaign covered.
    """
    s = settings()
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return HeatExplanation(status="error", error_message="Coordinates are invalid.").model_dump()
    try:
        rows = run(load_sql("explain_point"), tool="explain_heat_offset", lat=float(lat), lon=float(lon))
    except Exception as exc:  # surface as data; never raise into the agent loop
        log.exception("explain_heat_offset failed")
        return HeatExplanation(status="error",
                               error_message=f"The heat model could not be reached ({type(exc).__name__}).").model_dump()

    if not rows or not rows[0].get("in_footprint") or rows[0].get("geo_id") is None:
        return HeatExplanation(
            status="out_of_scope", lat=lat, lon=lon,
            error_message=(f"That location is outside the area {s.city}'s heat campaign covered, "
                           "so the model has no basis for a prediction there."),
        ).model_dump()

    r = rows[0]
    offset = round(float(r["predicted_offset_f"]), 1)
    drivers = _drivers(r["drivers"])
    top = ", ".join(f"{d.attribution_f:+.1f}°F from {d.label}" for d in drivers[:3])
    implied = round(forecast_high_f + offset, 0) if forecast_high_f > 0 else None
    out = HeatExplanation(
        lat=lat, lon=lon, geo_id=r["geo_id"],
        predicted_offset_f=offset, baseline_offset_f=float(r["baseline_offset_f"]),
        drivers=drivers, forecast_high_f=forecast_high_f or None, implied_local_high_f=implied,
        summary=f"Runs {offset:+.1f}°F vs. the {s.city} average ({top}).",
        model_version=s.model_id,
    )
    if tool_context is not None:
        tool_context.state["last_explained"] = out.model_dump()
    return out.model_dump()


# Track-specific weighting of hazard vs. vulnerability. A design decision: record it in DECISIONS.md.
TRACK_WEIGHTS = {
    "today":  {"hazard": 0.5, "no_vehicle_rate": 0.25, "median_age": 0.15, "poverty_rate": 0.10},
    "budget": {"hazard": 0.5, "poverty_rate": 0.2, "no_vehicle_rate": 0.15, "pop": 0.15},
    "decade": {"hazard": 0.7, "pop": 0.2, "poverty_rate": 0.1},
}


def rank_candidate_sites(k: int = 5, min_spacing_m: int = 800, unmeasured_only: bool = False,
                         tool_context: ToolContext | None = None) -> dict:
    """Ranks the best locations for heat help (cooling centers, hydration, trees) in the city.

    Combines the BigQuery ML predicted heat offset with who lives there (vehicle access, age,
    poverty, population), weighted for the team's track. Sites are kept at least
    min_spacing_m apart so they don't cluster on one block.

    Args:
        k: How many sites to return (1-15).
        min_spacing_m: Minimum distance between returned sites, in meters.
        unmeasured_only: If true, only return locations no volunteer measured, to show the model
            generalizing.

    Returns:
        dict with status and `sites`: rank, site_id, lat, lon, predicted_offset_f, drivers,
        demographics, score and a one-line reason each.
    """
    s = settings()
    k = max(1, min(int(k), 15))
    w = TRACK_WEIGHTS.get(s.track, TRACK_WEIGHTS["budget"])
    rows = run(load_sql("rank_sites"), tool="rank_candidate_sites",
               w_hazard=w.get("hazard", 0.5), w_novehicle=w.get("no_vehicle_rate", 0.0),
               w_age=w.get("median_age", 0.0), w_poverty=w.get("poverty_rate", 0.0),
               w_pop=w.get("pop", 0.0), unmeasured_only=bool(unmeasured_only))

    chosen: list[dict] = []
    for r in rows:  # rows arrive sorted by score desc; greedy spatial de-duplication
        if all(_meters(r, c) >= min_spacing_m for c in chosen):
            chosen.append(r)
        if len(chosen) == k:
            break
    if not chosen:
        return {"status": "no_data", "error_message": "No scored locations are available yet.", "sites": []}

    sites = []
    for i, r in enumerate(chosen, 1):
        drivers = _drivers(r["drivers"])
        sites.append({
            "rank": i, "site_id": r["point_id"], "lat": r["lat"], "lon": r["lon"],
            "predicted_offset_f": round(r["predicted_offset_f"], 1),
            "drivers": [d.model_dump() for d in drivers[:3]],
            "demographics": {k2: r[k2] for k2 in ("geo_id", "total_pop", "median_age",
                                                    "poverty_rate", "no_vehicle_rate")},
            "unmeasured": r["unmeasured"],
            "score": round(r["score"], 3),
            "why": (f"{r['predicted_offset_f']:+.1f}°F vs. city average, driven by "
                    f"{drivers[0].label if drivers else 'local conditions'}; "
                    f"{(r['no_vehicle_rate'] or 0):.0%} of households have no car."),
        })
    if tool_context is not None:
        tool_context.state["last_ranked_sites"] = sites
    return {"status": "ok", "track": s.track, "weights": w, "model_version": s.model_id, "sites": sites}


def _meters(a: dict, b: dict) -> float:
    # equirectangular approximation, fine at city scale
    x = math.radians(b["lon"] - a["lon"]) * math.cos(math.radians((a["lat"] + b["lat"]) / 2))
    y = math.radians(b["lat"] - a["lat"])
    return 6_371_000 * math.hypot(x, y)
