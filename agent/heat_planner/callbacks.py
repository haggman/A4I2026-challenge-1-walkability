"""Deterministic before_tool_callback and after_tool_callback guardrails."""
from __future__ import annotations

import logging
from typing import Any

from .config import Settings
from .schemas import ToolResult

log = logging.getLogger(__name__)

ALLOWED_MCP_TOOLS: frozenset[str] = frozenset(
    {
        "explain_point",
        "rank_sites_pool",
        "vulnerable_population",
        "site_hot_days",
        "city_heat_days_by_year",
        "tract_profile",
        "equity_audit",
        "hottest_measured_cells",
        "hottest_predicted_cells",
        "city_baseline",
        "tract_layer",
    }
)

ALLOWED_DATA_TOOLS: frozenset[str] = frozenset(
    {
        "resolve_location",
        "resolve_atlanta_location",
        "explain_heat_offset",
        "rank_candidate_sites",
        "compare_sites",
        "get_heat_frequency",
        "get_area_demographics",
        "get_walkable_demographics",
        "run_equity_audit",
        "assemble_placement_recommendation",
        *ALLOWED_MCP_TOOLS,
    }
)


def check_atlanta_metro_bounds(lat: float, lon: float) -> dict[str, Any] | None:
    """Return an `out_of_scope` ToolResult dict if (lat, lon) lies outside Atlanta metro bounds."""
    s = Settings()
    if not (s.lat_min <= lat <= s.lat_max and s.lon_min <= lon <= s.lon_max):
        return ToolResult(
            status="out_of_scope",
            data={"lat": lat, "lon": lon, "in_footprint": False},
            error_message=(
                f"Coordinates ({lat:.4f}, {lon:.4f}) lie outside the {s.city} metro bounding box "
                f"([{s.lat_min}, {s.lat_max}] N, [{s.lon_min}, {s.lon_max}] W). "
                f"Our BigQuery ML model ({s.bqml_model_id}) only has support inside {s.city}'s "
                "Heat Watch campaign footprint."
            ),
            model_version=s.bqml_model_id,
        ).model_dump()
    return None


def before_tool_callback(
    tool: Any, args: dict[str, Any], tool_context: Any = None
) -> dict[str, Any] | None:
    """Validate stage allowlist, Atlanta coordinate bounds, and parameter ranges before running a tool."""
    tool_name = getattr(tool, "name", None) or getattr(tool, "__name__", str(tool))
    if tool_name not in ALLOWED_DATA_TOOLS:
        return ToolResult(
            status="error",
            error_message=f"Tool '{tool_name}' is not in ALLOWED_DATA_TOOLS.",
        ).model_dump()

    # Coordinate bounds check (except resolve_location which takes a query string)
    if "lat" in args and "lon" in args and args["lat"] is not None and args["lon"] is not None:
        try:
            lat_f = float(args["lat"])
            lon_f = float(args["lon"])
        except (TypeError, ValueError):
            return ToolResult(
                status="error",
                error_message=f"Invalid coordinates lat={args.get('lat')}, lon={args.get('lon')}.",
            ).model_dump()
        bounds_err = check_atlanta_metro_bounds(lat_f, lon_f)
        if bounds_err is not None:
            return bounds_err

    # Parameter bounds check
    for k_key in ("k", "k_sites"):
        if k_key in args and args[k_key] is not None:
            k_val = int(args[k_key])
            if not (1 <= k_val <= 10):
                args[k_key] = max(1, min(k_val, 10))
    if "min_spacing_m" in args and args["min_spacing_m"] is not None:
        sp_val = int(args["min_spacing_m"])
        if not (250 <= sp_val <= 10000):
            args["min_spacing_m"] = max(250, min(sp_val, 10000))
    if "radius_m" in args and args["radius_m"] is not None:
        r_val = float(args["radius_m"])
        if not (100.0 <= r_val <= 5000.0):
            args["radius_m"] = max(100.0, min(r_val, 5000.0))

    return None


def after_tool_callback(
    tool: Any,
    args: dict[str, Any],
    tool_context: Any,
    tool_response: dict[str, Any] | Any,
) -> dict[str, Any] | None:
    """Normalize empty results or out-of-footprint responses after tool execution."""
    if not isinstance(tool_response, dict):
        return None
    data = tool_response.get("data")
    if isinstance(data, dict) and data.get("in_footprint") is False:
        if tool_response.get("status") != "out_of_scope":
            tool_response["status"] = "out_of_scope"
            return tool_response
    return None
