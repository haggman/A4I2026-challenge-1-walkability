"""Census tract demographics & walkable catchment lookup tool via MCP Toolbox."""
from __future__ import annotations

import logging
from typing import Any

from google.adk.tools import ToolContext

from ..callbacks import check_atlanta_metro_bounds
from ..config import Settings
from ..mcp_client import invoke_mcp_tool
from ..schemas import Provenance, ToolResult
from .location import build_google_maps_urls, infer_atlanta_neighborhood

log = logging.getLogger(__name__)


def get_area_demographics(
    lat: float,
    lon: float,
    radius_m: float = 800.0,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Return sentinel-cleaned ACS census tract demographics for the tract nearest
    to (lat, lon), plus the walkable catchment population within `radius_m` meters
    and the population-weighted Atlanta city baseline for comparison.

    Args:
        lat: Latitude in decimal degrees (WGS84, e.g. 33.7568).
        lon: Longitude in decimal degrees (WGS84, e.g. -84.4126).
        radius_m: Walkable catchment radius in meters (default 800.0 m ≈ 10-minute walk).
    """
    s = Settings()
    radius_m = max(100.0, min(float(radius_m), 5000.0))

    bounds_err = check_atlanta_metro_bounds(float(lat), float(lon))
    if bounds_err is not None:
        return bounds_err

    prov_list: list[Provenance] = []
    try:
        tract_rows, _ = invoke_mcp_tool(
            "tract_profile",
            tool_name="get_area_demographics",
            provenance_list=prov_list,
            lat=float(lat),
            lon=float(lon),
        )
        vp_rows, _ = invoke_mcp_tool(
            "vulnerable_population",
            tool_name="get_area_demographics",
            provenance_list=prov_list,
            lat=float(lat),
            lon=float(lon),
            radius_m=float(radius_m),
        )
        base_rows, _ = invoke_mcp_tool(
            "city_baseline",
            tool_name="get_area_demographics",
            provenance_list=prov_list,
        )
    except Exception as exc:
        log.exception("get_area_demographics failed")
        return ToolResult(status="error", error_message=str(exc)).model_dump()

    if not tract_rows:
        return ToolResult(
            status="not_found",
            error_message=(
                f"No Atlanta census tract found within 15 km of ({lat:.4f}, {lon:.4f})."
            ),
            provenance=prov_list,
        ).model_dump()

    row = tract_rows[0]
    vp = vp_rows[0] if vp_rows else {}
    base = base_rows[0] if base_rows else {}
    geo_id = str(row["geo_id"]).zfill(11)
    neighborhood = infer_atlanta_neighborhood(lat, lon, geo_id)
    urls = build_google_maps_urls(lat, lon, neighborhood)

    walkable_catchment = {
        "geo_id": geo_id,
        "radius_m": radius_m,
        "tract_count": int(vp.get("tracts_within_radius") or vp.get("tract_count") or 1),
        "tract_geo_ids": list(vp.get("tract_geo_ids") or [geo_id]),
        "total_pop": int(vp.get("population_within_radius") or vp.get("total_pop") or row.get("total_pop") or 0),
        "pop_65_plus": int(vp.get("pop_65_plus_within_radius") or vp.get("pop_65_plus") or row.get("pop_65_plus") or 0),
        "households": int(vp.get("households_within_radius") or vp.get("households") or row.get("households") or 0),
        "car_free_households": int(
            vp.get("car_free_households_within_radius")
            or vp.get("car_free_households")
            or row.get("car_free_households")
            or 0
        ),
        "share_65_plus": float(
            vp.get("share_65_plus_within_radius")
            if vp.get("share_65_plus_within_radius") is not None
            else (vp.get("share_65_plus") if vp.get("share_65_plus") is not None else (row.get("share_65_plus") or 0.0))
        ),
        "no_vehicle_rate": float(
            vp.get("no_vehicle_rate_within_radius")
            if vp.get("no_vehicle_rate_within_radius") is not None
            else (vp.get("no_vehicle_rate") if vp.get("no_vehicle_rate") is not None else (row.get("no_vehicle_rate") or 0.0))
        ),
        "poverty_rate": float(
            vp.get("pop_weighted_poverty_rate")
            if vp.get("pop_weighted_poverty_rate") is not None
            else (vp.get("poverty_rate") if vp.get("poverty_rate") is not None else (row.get("poverty_rate") or 0.0))
        ),
        "median_income": (
            float(vp["median_income"])
            if vp.get("median_income") is not None
            else (float(row["median_income"]) if row.get("median_income") is not None else None)
        ),
    }

    payload = {
        "lat": round(float(lat), 5),
        "lon": round(float(lon), 5),
        "geo_id": geo_id,
        "neighborhood": neighborhood,
        **walkable_catchment,
        "tract": {
            "geo_id": geo_id,
            "meters_to_tract_center": row.get("meters_to_tract_center"),
            "total_pop": row.get("total_pop"),
            "pop_65_plus": row.get("pop_65_plus"),
            "share_65_plus": row.get("share_65_plus"),
            "car_free_households": row.get("car_free_households"),
            "no_vehicle_rate": row.get("no_vehicle_rate"),
            "poverty_rate": row.get("poverty_rate"),
            "median_income": row.get("median_income"),
            "median_age": row.get("median_age"),
            "households": row.get("households"),
            "housing_units": row.get("housing_units"),
            "median_year_built": row.get("median_year_built"),
            "pop_density_km2": row.get("pop_density_km2"),
            "housing_density_km2": row.get("housing_density_km2"),
        },
        "walkable_catchment": walkable_catchment,
        "city_baseline": {
            "city_poverty_rate": base.get("city_poverty_rate"),
            "city_no_vehicle_rate": base.get("city_no_vehicle_rate"),
            "city_share_65_plus": base.get("city_share_65_plus"),
            "city_median_income_usd": base.get("city_median_income_usd"),
            "city_median_age_years": base.get("city_median_age_years"),
        },
        **urls,
    }

    if tool_context is not None:
        tool_context.state["last_demographics"] = payload
        existing_prov = list(tool_context.state.get("turn_provenance") or [])
        existing_prov.extend(p.model_dump() for p in prov_list)
        tool_context.state["turn_provenance"] = existing_prov

    return ToolResult(
        status="success",
        data=payload,
        provenance=prov_list,
        model_version=s.bqml_model_id,
        caveats=[
            "Demographics come from sentinel-cleaned ACS 2020 5-year tract estimates (a4i_semantic.tract_features).",
            "Demographic variables are used for planner context, ranking, and post-hoc equity auditing — never as BQML heat-model features.",
        ],
    ).model_dump()


def get_walkable_demographics(
    lat: float,
    lon: float,
    radius_m: float = 800.0,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Alias for get_area_demographics returning walkable catchment and tract demographics."""
    return get_area_demographics(lat=lat, lon=lon, radius_m=radius_m, tool_context=tool_context)
