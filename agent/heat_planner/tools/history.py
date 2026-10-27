"""GHCN daily weather-station heat-frequency tool (2019-2025) via MCP Toolbox."""
from __future__ import annotations

import logging
from typing import Any

from google.adk.tools import ToolContext

from ..config import Settings
from ..mcp_client import invoke_mcp_tool
from ..schemas import CityHeatFrequencySummary, Provenance, ToolResult

log = logging.getLogger(__name__)


def _ols_slope_per_decade(years: list[int], values: list[float]) -> float | None:
    n = len(years)
    if n < 3:
        return None
    mean_x = sum(years) / n
    mean_y = sum(values) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(years, values))
    den = sum((x - mean_x) ** 2 for x in years)
    if den == 0:
        return 0.0
    return round((num / den) * 10.0, 2)


def get_heat_frequency(
    threshold_f: float = 95.0,
    offset_f: float = 0.0,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Query multi-year GHCN weather-station history (2019-2025) for Atlanta to count
    how many days per year reach or exceed 90°F, 95°F, and 100°F (plus site-specific
    equivalent days when `offset_f > 0`).

    Never uses Heat Watch traverse observations to answer frequency questions.

    Args:
        threshold_f: Daily maximum temperature threshold in °F (default 95.0; common values: 90, 95, 100).
        offset_f: Optional site heat offset in °F above the city mean (default 0.0).
    """
    s = Settings()
    prov_list: list[Provenance] = []
    try:
        rows, _ = invoke_mcp_tool(
            "city_heat_days_by_year",
            tool_name="get_heat_frequency",
            provenance_list=prov_list,
        )
        site_rows, _ = invoke_mcp_tool(
            "site_hot_days",
            tool_name="get_heat_frequency",
            provenance_list=prov_list,
            offset_f=round(float(offset_f), 2),
        )
    except Exception as exc:
        log.exception("get_heat_frequency failed")
        return ToolResult(status="error", error_message=str(exc)).model_dump()

    if not rows:
        return ToolResult(
            status="not_found",
            error_message=f"No GHCN station history rows found for {s.city}.",
            provenance=prov_list,
        ).model_dump()

    years = [int(r["year"]) for r in rows]
    days_90 = [float(r.get("days_ge_90_f") or r.get("days_ge_90f") or 0.0) for r in rows]
    days_95 = [float(r.get("days_ge_95_f") or r.get("days_ge_95f") or 0.0) for r in rows]
    days_100 = [float(r.get("days_ge_100_f") or r.get("days_ge_100f") or 0.0) for r in rows]
    max_temps = [float(r.get("hottest_temp_f") or r.get("hottest_day_f") or 0.0) for r in rows]

    avg_90 = round(sum(days_90) / len(days_90), 1)
    avg_95 = round(sum(days_95) / len(days_95), 1)
    avg_100 = round(sum(days_100) / len(days_100), 1)
    hottest_f = round(max(max_temps), 1)
    trend_decade = _ols_slope_per_decade(years, days_95)

    sr = site_rows[0] if site_rows else {}
    site_avg_95 = float(
        sr.get("mean_days_ge_95f_equiv_per_yr")
        or sr.get("expected_days_ge_95f_equiv")
        or avg_95
    )
    extra_site_95 = float(
        sr.get("extra_days_ge_95f_equiv_per_yr")
        or sr.get("extra_days_ge_95f_equiv")
        or round(site_avg_95 - avg_95, 1)
    )

    summary = CityHeatFrequencySummary(
        years_covered=f"{min(years)}-{max(years)}",
        full_years_count=len(years),
        avg_days_ge_90f=avg_90,
        avg_days_ge_95f=avg_95,
        avg_days_ge_100f=avg_100,
        hottest_temp_recorded_f=hottest_f,
        trend_days_per_decade=trend_decade,
        by_year=rows,
    )

    payload = summary.model_dump()
    payload.update(
        {
            "city": {
                "name": s.city,
                "threshold_f": float(threshold_f),
                "offset_f": float(offset_f),
                "years_covered": summary.years_covered,
                "full_years_count": summary.full_years_count,
            },
            "avg_days_per_year": avg_95 if threshold_f == 95.0 else (avg_90 if threshold_f <= 90.0 else avg_100),
            "site_avg_days_per_year": site_avg_95,
            "extra_site_days_per_year": extra_site_95,
        }
    )

    if tool_context is not None:
        tool_context.state["last_heat_frequency"] = payload
        existing_prov = list(tool_context.state.get("turn_provenance") or [])
        existing_prov.extend(p.model_dump() for p in prov_list)
        tool_context.state["turn_provenance"] = existing_prov

    return ToolResult(
        status="success",
        data=payload,
        provenance=prov_list,
        model_version=s.bqml_model_id,
        caveats=[
            "Computed from 8 Atlanta-area NOAA GHCN daily weather stations (2019-2025, full years with >=300 reporting days).",
            "A 7-year window (2019-2025) captures interannual variability (55 days >=95°F in 2019 vs. 23-26 days in 2023-2024) and is shorter than the 30-year WMO climatological standard.",
        ],
    ).model_dump()
