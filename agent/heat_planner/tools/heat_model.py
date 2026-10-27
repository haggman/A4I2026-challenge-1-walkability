"""Tools that invoke the BigQuery ML heat-offset model (offset_model_v1) via MCP Toolbox."""
from __future__ import annotations

import logging
from typing import Any

from google.adk.tools import ToolContext

from ..callbacks import check_atlanta_metro_bounds
from ..config import Settings
from ..mcp_client import invoke_mcp_tool
from ..schemas import (
    CatchmentDemographics,
    Driver,
    HeatExplanation,
    Provenance,
    SiteAssessment,
    SiteHotDays,
    ToolResult,
)
from .location import build_google_maps_urls, haversine_m, infer_atlanta_neighborhood

log = logging.getLogger(__name__)


def _build_site_hot_days(
    offset_f: float,
    provenance_list: list[Provenance],
    tool_name: str,
) -> SiteHotDays:
    rows, _ = invoke_mcp_tool(
        "site_hot_days",
        tool_name=tool_name,
        provenance_list=provenance_list,
        offset_f=round(float(offset_f), 2),
    )
    r = rows[0] if rows else {}
    return SiteHotDays(
        city_days_ge_90f_per_yr=float(r.get("city_days_ge_90f_per_yr") or 78.0),
        city_days_ge_95f_per_yr=float(
            r.get("city_baseline_days_ge_95f_per_yr")
            or r.get("city_days_ge_95f_per_yr")
            or 23.9
        ),
        city_days_ge_100f_per_yr=float(r.get("city_days_ge_100f_per_yr") or 1.6),
        expected_days_ge_90f_equiv=float(
            r.get("mean_days_ge_90f_equiv_per_yr")
            or r.get("expected_days_ge_90f_equiv")
            or 88.0
        ),
        expected_days_ge_95f_equiv=float(
            r.get("mean_days_ge_95f_equiv_per_yr")
            or r.get("expected_days_ge_95f_equiv")
            or 35.0
        ),
        expected_days_ge_100f_equiv=float(
            r.get("mean_days_ge_100f_equiv_per_yr")
            or r.get("expected_days_ge_100f_equiv")
            or 4.0
        ),
        extra_days_ge_95f_equiv=float(
            r.get("extra_days_ge_95f_equiv_per_yr")
            or r.get("extra_days_ge_95f_equiv")
            or 11.1
        ),
    )


def _build_catchment_demographics(
    lat: float,
    lon: float,
    geo_id: str,
    radius_m: float,
    fallback_row: dict[str, Any],
    provenance_list: list[Provenance],
    tool_name: str,
) -> CatchmentDemographics:
    rows, _ = invoke_mcp_tool(
        "vulnerable_population",
        tool_name=tool_name,
        provenance_list=provenance_list,
        lat=float(lat),
        lon=float(lon),
        radius_m=float(radius_m),
    )
    vp = rows[0] if rows else {}
    t_count = int(vp.get("tracts_within_radius") or vp.get("tract_count") or 0)
    if vp and t_count > 0:
        return CatchmentDemographics(
            geo_id=str(geo_id).zfill(11),
            radius_m=float(radius_m),
            tract_count=t_count,
            tract_geo_ids=[str(g).zfill(11) for g in (vp.get("tract_geo_ids") or [geo_id])],
            total_pop=int(
                vp.get("population_within_radius")
                or vp.get("total_pop")
                or fallback_row.get("total_pop")
                or fallback_row.get("population")
                or 0
            ),
            pop_65_plus=int(
                vp.get("pop_65_plus_within_radius")
                or vp.get("pop_65_plus")
                or fallback_row.get("pop_65_plus")
                or 0
            ),
            share_65_plus=float(
                vp.get("share_65_plus_within_radius")
                if vp.get("share_65_plus_within_radius") is not None
                else (
                    vp.get("share_65_plus")
                    if vp.get("share_65_plus") is not None
                    else (fallback_row.get("share_65_plus") or 0.0)
                )
            ),
            households=int(
                vp.get("households_within_radius")
                or vp.get("households")
                or fallback_row.get("households")
                or 0
            ),
            car_free_households=int(
                vp.get("car_free_households_within_radius")
                or vp.get("car_free_households")
                or fallback_row.get("car_free_households")
                or 0
            ),
            no_vehicle_rate=float(
                vp.get("no_vehicle_rate_within_radius")
                if vp.get("no_vehicle_rate_within_radius") is not None
                else (
                    vp.get("no_vehicle_rate")
                    if vp.get("no_vehicle_rate") is not None
                    else (fallback_row.get("no_vehicle_rate") or 0.0)
                )
            ),
            poverty_rate=float(
                vp.get("pop_weighted_poverty_rate")
                if vp.get("pop_weighted_poverty_rate") is not None
                else (
                    vp.get("poverty_rate")
                    if vp.get("poverty_rate") is not None
                    else (fallback_row.get("poverty_rate") or 0.0)
                )
            ),
            median_income=(
                float(vp["median_income"])
                if vp.get("median_income") is not None
                else (
                    float(fallback_row["median_income"])
                    if fallback_row.get("median_income") is not None
                    else None
                )
            ),
        )

    # Fallback to the tract itself if no tract centroid falls inside radius_m
    return CatchmentDemographics(
        geo_id=str(geo_id).zfill(11),
        radius_m=float(radius_m),
        tract_count=1,
        tract_geo_ids=[str(geo_id).zfill(11)],
        total_pop=int(fallback_row.get("total_pop") or fallback_row.get("population") or 0),
        pop_65_plus=int(fallback_row.get("pop_65_plus") or 0),
        share_65_plus=float(fallback_row.get("share_65_plus") or 0.0),
        households=int(fallback_row.get("households") or 0),
        car_free_households=int(fallback_row.get("car_free_households") or 0),
        no_vehicle_rate=float(fallback_row.get("no_vehicle_rate") or 0.0),
        poverty_rate=float(fallback_row.get("poverty_rate") or 0.0),
        median_income=(
            float(fallback_row["median_income"])
            if fallback_row.get("median_income") is not None
            else None
        ),
    )


def explain_heat_offset(
    lat: float,
    lon: float,
    forecast_high_f: float = 0.0,
    top_k: int = 5,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Predict how much hotter or cooler (lat, lon) runs vs. the Atlanta campaign average,
    and explain which physical / built-environment features drive that offset.

    Calls BigQuery ML `ML.EXPLAIN_PREDICT` on `a4i_ml.offset_model_v1` via MCP Toolbox
    `explain_point`, plus `vulnerable_population` and `site_hot_days`.
    Refuses with `status='out_of_scope'` if (lat, lon) is outside the campaign footprint.

    Args:
        lat: Latitude in decimal degrees (WGS84, e.g. 33.7568).
        lon: Longitude in decimal degrees (WGS84, e.g. -84.4126).
        forecast_high_f: Optional NWS forecast high in °F (e.g. 98.0) to compute implied site feel.
        top_k: Number of top feature attributions to return (1..8, default 5).
    """
    s = Settings()
    top_k = max(1, min(int(top_k), 8))

    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return ToolResult(
            status="not_found",
            error_message=f"Coordinates ({lat}, {lon}) are outside valid WGS84 bounds.",
        ).model_dump()

    bounds_err = check_atlanta_metro_bounds(float(lat), float(lon))
    if bounds_err is not None:
        return bounds_err

    prov_list: list[Provenance] = []
    try:
        rows, _ = invoke_mcp_tool(
            "explain_point",
            tool_name="explain_heat_offset",
            provenance_list=prov_list,
            lat=float(lat),
            lon=float(lon),
        )
    except Exception as exc:
        log.exception("explain_heat_offset failed")
        return ToolResult(status="error", error_message=str(exc)).model_dump()

    if not rows:
        return ToolResult(
            status="not_found",
            error_message=(
                f"No census tract within 10 km of ({lat:.4f}, {lon:.4f}). "
                f"This assistant only covers {s.city}, GA."
            ),
            provenance=prov_list,
        ).model_dump()

    row = rows[0]
    if not row.get("in_footprint") or row.get("predicted_offset_f") is None:
        return ToolResult(
            status="out_of_scope",
            data={
                "lat": float(lat),
                "lon": float(lon),
                "in_footprint": False,
                "km_from_center": row.get("km_from_center"),
                "nearest_tract": row.get("geo_id"),
            },
            error_message=(
                f"({lat:.4f}, {lon:.4f}) is outside {s.city}'s Heat Watch campaign footprint "
                f"({row.get('km_from_center')} km from the campaign centroid). "
                "The model has no training support outside the measured campaign boundary "
                "and refuses to extrapolate."
            ),
            provenance=prov_list,
            model_version=s.bqml_model_id,
        ).model_dump()

    pred_offset = round(float(row["predicted_offset_f"]), 2)
    geo_id = str(row["geo_id"]).zfill(11)
    drivers = [
        Driver(
            feature=str(d["feature"]),
            attribution=round(
                float(
                    d["attribution"]
                    if d.get("attribution") is not None
                    else d.get("attribution_f", 0.0)
                ),
                3,
            ),
        )
        for d in (row.get("drivers") or [])[:top_k]
    ]
    hot_days = _build_site_hot_days(pred_offset, prov_list, "explain_heat_offset")

    # Fetch tract fallback & walkable catchment
    tract_rows, _ = invoke_mcp_tool(
        "tract_profile",
        tool_name="explain_heat_offset",
        provenance_list=prov_list,
        lat=float(lat),
        lon=float(lon),
    )
    tract_fallback = tract_rows[0] if tract_rows else {}
    demographics = _build_catchment_demographics(
        float(lat),
        float(lon),
        geo_id,
        800.0,
        tract_fallback,
        prov_list,
        "explain_heat_offset",
    )

    implied_f = (
        round(float(forecast_high_f) + pred_offset, 1)
        if forecast_high_f and float(forecast_high_f) > 0
        else None
    )
    neighborhood = infer_atlanta_neighborhood(float(row["lat"]), float(row["lon"]), geo_id)
    urls = build_google_maps_urls(float(row["lat"]), float(row["lon"]), neighborhood)

    result = HeatExplanation(
        lat=float(row["lat"]),
        lon=float(row["lon"]),
        geo_id=geo_id,
        in_footprint=True,
        predicted_offset_f=pred_offset,
        baseline_offset_f=round(float(row.get("baseline_offset_f") or 0.0), 2),
        campaign_mean_f=round(float(row.get("campaign_mean_f") or 82.1), 1),
        forecast_high_f=float(forecast_high_f) if implied_f is not None else None,
        forecast_implied_f=implied_f,
        drivers=drivers,
        measured_nearby=bool(row.get("measured_nearby", False)),
        expected_days_ge_95f_equiv_per_yr=hot_days.expected_days_ge_95f_equiv,
        city_days_ge_95f_per_yr=hot_days.city_days_ge_95f_per_yr,
        extra_days_ge_95f_equiv_per_yr=hot_days.extra_days_ge_95f_equiv,
        model_version=s.bqml_model_id,
    )

    top_drv = drivers[0] if drivers else Driver(feature="built_environment", attribution=0.0)
    site_assessment = SiteAssessment(
        rank=1,
        point_id=f"p_{float(row['lat']):.4f}_{float(row['lon']):.4f}",
        lat=float(row["lat"]),
        lon=float(row["lon"]),
        geo_id=geo_id,
        neighborhood=neighborhood,
        predicted_offset_f=pred_offset,
        campaign_mean_f=result.campaign_mean_f,
        forecast_high_f=result.forecast_high_f,
        forecast_implied_f=result.forecast_implied_f,
        priority_score=round(pred_offset, 3),
        unmeasured=not bool(row.get("measured_nearby", False)),
        drivers=drivers,
        demographics=demographics,
        hot_days=hot_days,
        google_maps_url=urls["google_maps_url"],
        google_maps_walking_url=urls["google_maps_walking_url"],
        why_here=(
            f"Predicted {pred_offset:+.2f}°F relative to the {s.city} campaign average "
            f"({result.campaign_mean_f:.1f}°F), driven primarily by {top_drv.feature} "
            f"({top_drv.attribution:+.3f}°F) in {neighborhood} (Tract {geo_id})."
        ),
    )

    payload = result.model_dump()
    payload["neighborhood"] = neighborhood
    payload["demographics"] = demographics.model_dump()
    payload["hot_days"] = hot_days.model_dump()
    payload["site_assessment"] = site_assessment.model_dump()
    payload.update(urls)

    if tool_context is not None:
        tool_context.state["last_explained"] = payload
        existing_prov = list(tool_context.state.get("turn_provenance") or [])
        existing_prov.extend(p.model_dump() for p in prov_list)
        tool_context.state["turn_provenance"] = existing_prov

    return ToolResult(
        status="success",
        data=payload,
        provenance=prov_list,
        model_version=s.bqml_model_id,
        caveats=[
            "Predicted offset is °F relative to the Atlanta Heat Watch campaign mean (82.1°F), not a weather forecast.",
            "Attributions reflect built-environment associations in a4i_ml.offset_model_v1, not causal effects of interventions.",
        ],
    ).model_dump()


def rank_candidate_sites(
    k: int = 3,
    min_spacing_m: int = 2000,
    radius_m: float = 800.0,
    unmeasured_only: bool = False,
    forecast_high_f: float = 0.0,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Rank the top K candidate cooling-center locations across Atlanta's 250 m prediction grid
    with greedy Haversine spacing (`>= min_spacing_m` meters between selected sites).

    Uses the transparent priority score from `a4i_ml.grid_predictions` + `a4i_semantic.tract_features`:
      `priority_score = 0.45*predicted_offset_f + 0.25*(no_vehicle_rate*2) + 0.15*(poverty_rate*2)
                        + 0.10*(share_65_plus*2) + 0.05*LOG10(total_pop + 1)`
    Vulnerability enters ONLY at this ranking step — never inside the BQML heat model.
    Returns both the top `k` spaced sites (`sites`) and runner-up candidates (`runner_up_sites`).

    Args:
        k: Number of candidate sites to select (1..10, default 3).
        min_spacing_m: Minimum distance in meters between selected sites (default 2000 m).
        radius_m: Walkable catchment radius in meters (default 800.0 m ≈ 10-min walk).
        unmeasured_only: If True, restrict to grid points >150m from any Heat Watch reading.
        forecast_high_f: Optional NWS forecast high in °F (e.g. 98.0) to compute implied site feel.
    """
    s = Settings()
    k = max(1, min(int(k), 10))
    min_spacing_m = max(0, min(int(min_spacing_m), 10000))
    radius_m = max(100.0, min(float(radius_m), 5000.0))

    prov_list: list[Provenance] = []
    try:
        pool_rows, _ = invoke_mcp_tool(
            "rank_sites_pool",
            tool_name="rank_candidate_sites",
            provenance_list=prov_list,
            unmeasured_only=bool(unmeasured_only),
            limit=25,
        )
    except Exception as exc:
        log.exception("rank_candidate_sites failed")
        return ToolResult(status="error", error_message=str(exc)).model_dump()

    if not pool_rows:
        return ToolResult(
            status="no_data",
            error_message="No candidate grid points returned from rank_sites_pool.",
            provenance=prov_list,
        ).model_dump()

    # Greedy Haversine spacing selection across the tract-deduplicated pool
    selected_entries: list[tuple[dict[str, Any], int | None]] = []
    runner_up_entries: list[tuple[dict[str, Any], int | None]] = []

    for r in pool_rows:
        lat_r = float(r["lat"])
        lon_r = float(r["lon"])
        if len(selected_entries) < k:
            conflict_rank: int | None = None
            for idx_sel, (sel_r, _) in enumerate(selected_entries, start=1):
                dist_m = haversine_m(lat_r, lon_r, float(sel_r["lat"]), float(sel_r["lon"]))
                if dist_m < min_spacing_m:
                    conflict_rank = idx_sel
                    break
            if conflict_rank is None:
                selected_entries.append((r, None))
            else:
                runner_up_entries.append((r, conflict_rank))
        else:
            runner_up_entries.append((r, None))

    def _to_site_assessment(
        r: dict[str, Any],
        rank_num: int,
        conflict_rank: int | None,
        enrich_via_mcp: bool,
    ) -> SiteAssessment:
        lat_val = float(r["lat"])
        lon_val = float(r["lon"])
        geo_id = str(r["geo_id"]).zfill(11)
        pred_offset = round(float(r["predicted_offset_f"]), 2)
        prio_score = round(float(r["priority_score"]), 3)
        drivers = [
            Driver(
                feature=str(d["feature"]),
                attribution=round(
                    float(
                        d["attribution"]
                        if d.get("attribution") is not None
                        else d.get("attribution_f", 0.0)
                    ),
                    3,
                ),
            )
            for d in (r.get("drivers") or [])
        ]
        top_driver = drivers[0] if drivers else Driver(feature="built_density", attribution=0.0)

        if enrich_via_mcp:
            hot_days = _build_site_hot_days(pred_offset, prov_list, "rank_candidate_sites")
            dem = _build_catchment_demographics(
                lat_val, lon_val, geo_id, radius_m, r, prov_list, "rank_candidate_sites"
            )
        else:
            hot_days = SiteHotDays(
                city_days_ge_90f_per_yr=78.0,
                city_days_ge_95f_per_yr=23.9,
                city_days_ge_100f_per_yr=1.6,
                expected_days_ge_90f_equiv=round(78.0 + pred_offset * 12.0, 1),
                expected_days_ge_95f_equiv=round(23.9 + pred_offset * 9.0, 1),
                expected_days_ge_100f_equiv=round(max(1.6, 1.6 + pred_offset * 2.5), 1),
                extra_days_ge_95f_equiv=round(pred_offset * 9.0, 1),
            )
            dem = CatchmentDemographics(
                geo_id=geo_id,
                radius_m=radius_m,
                tract_count=1,
                tract_geo_ids=[geo_id],
                total_pop=int(r.get("total_pop") or 0),
                pop_65_plus=int(r.get("pop_65_plus") or 0),
                share_65_plus=float(r.get("share_65_plus") or 0.0),
                households=int(r.get("households") or 0),
                car_free_households=int(r.get("car_free_households") or 0),
                no_vehicle_rate=float(r.get("no_vehicle_rate") or 0.0),
                poverty_rate=float(r.get("poverty_rate") or 0.0),
                median_income=(
                    float(r["median_income"]) if r.get("median_income") is not None else None
                ),
            )

        neighborhood = infer_atlanta_neighborhood(lat_val, lon_val, geo_id)
        urls = build_google_maps_urls(lat_val, lon_val, neighborhood)
        implied_f = (
            round(float(forecast_high_f) + pred_offset, 1)
            if forecast_high_f and float(forecast_high_f) > 0
            else None
        )
        nv_pct = f"{float(r.get('no_vehicle_rate') or dem.no_vehicle_rate) * 100:.1f}%"
        pov_pct = f"{float(r.get('poverty_rate') or dem.poverty_rate) * 100:.1f}%"
        s65_pct = f"{float(r.get('share_65_plus') or dem.share_65_plus) * 100:.1f}%"
        why = (
            f"Predicted {pred_offset:+.2f}°F above the {s.city} campaign average (82.1°F) "
            f"(~{hot_days.expected_days_ge_95f_equiv:.1f} days/yr of >=95°F-equivalent heat vs. "
            f"{hot_days.city_days_ge_95f_per_yr:.1f} citywide), driven by {top_driver.feature} "
            f"({top_driver.attribution:+.3f}°F) at an {'unmeasured' if r['unmeasured'] else 'measured'} "
            f"grid cell in {neighborhood} (Tract {geo_id}). Tract {geo_id} has {nv_pct} car-free "
            f"households ({int(r.get('car_free_households') or dem.car_free_households):,} HH), "
            f"{pov_pct} poverty, and {s65_pct} seniors 65+ ({int(r.get('pop_65_plus') or dem.pop_65_plus):,} seniors)."
        )
        return SiteAssessment(
            rank=rank_num,
            point_id=str(r["point_id"]),
            lat=lat_val,
            lon=lon_val,
            geo_id=geo_id,
            neighborhood=neighborhood,
            predicted_offset_f=pred_offset,
            campaign_mean_f=82.1,
            forecast_high_f=float(forecast_high_f) if implied_f is not None else None,
            forecast_implied_f=implied_f,
            priority_score=prio_score,
            unmeasured=bool(r["unmeasured"]),
            spacing_conflict_with_rank=conflict_rank,
            drivers=drivers,
            demographics=dem,
            hot_days=hot_days,
            google_maps_url=urls["google_maps_url"],
            google_maps_walking_url=urls["google_maps_walking_url"],
            why_here=why,
        )

    sites: list[SiteAssessment] = []
    for idx, (row_item, conflict) in enumerate(selected_entries, start=1):
        sites.append(_to_site_assessment(row_item, idx, conflict, enrich_via_mcp=True))

    runner_ups: list[SiteAssessment] = []
    max_runner_ups = max(0, 10 - len(sites))
    for offset_idx, (row_item, conflict) in enumerate(runner_up_entries[:max_runner_ups], start=1):
        rank_num = len(sites) + offset_idx
        # Enrich the top runner-up (#4) via MCP so compare_sites has full catchment & hot_days
        runner_ups.append(
            _to_site_assessment(row_item, rank_num, conflict, enrich_via_mcp=(offset_idx == 1))
        )

    serialized_sites = [site.model_dump() for site in sites]
    serialized_runners = [site.model_dump() for site in runner_ups]
    all_candidates = serialized_sites + serialized_runners

    if tool_context is not None:
        tool_context.state["last_ranked_sites"] = serialized_sites
        tool_context.state["last_ranked_candidates"] = all_candidates
        existing_prov = list(tool_context.state.get("turn_provenance") or [])
        existing_prov.extend(p.model_dump() for p in prov_list)
        tool_context.state["turn_provenance"] = existing_prov

    return ToolResult(
        status="success",
        data={
            "sites": serialized_sites,
            "runner_up_sites": serialized_runners,
            "min_spacing_m": min_spacing_m,
            "radius_m": radius_m,
            "unmeasured_only": unmeasured_only,
            "weights": {
                "hazard_offset": 0.45,
                "no_vehicle_rate_x2": 0.25,
                "poverty_rate_x2": 0.15,
                "share_65_plus_x2": 0.10,
                "log10_pop": 0.05,
            },
        },
        provenance=prov_list,
        model_version=s.bqml_model_id,
    ).model_dump()


def compare_sites(
    ranks: list[int] | None = None,
    site_a_lat: float = 0.0,
    site_a_lon: float = 0.0,
    site_b_lat: float = 0.0,
    site_b_lon: float = 0.0,
    site_a_label: str = "Candidate Site A",
    site_b_label: str = "Candidate Site B",
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Compare candidate cooling-center locations side-by-side for capital budget trade-offs.

    Supports two modes:
      1. Rank-based comparison (`ranks=[1, 2, 3, 4]`): compares the top recommended sites
         against runner-up candidate(s) (e.g., Site #4) using cached `last_ranked_candidates`
         (or automatically runs `rank_candidate_sites` if not yet cached).
      2. Coordinate-based comparison (`site_a_lat/lon` vs. `site_b_lat/lon`): compares two
         arbitrary coordinates using `explain_heat_offset`.

    Args:
        ranks: Optional list of candidate ranks to compare (default `[1, 2, 3, 4]`).
        site_a_lat: Optional latitude of Site A (when comparing two explicit coordinates).
        site_a_lon: Optional longitude of Site A.
        site_b_lat: Optional latitude of Site B.
        site_b_lon: Optional longitude of Site B.
        site_a_label: Human-readable label for Site A.
        site_b_label: Human-readable label for Site B.
    """
    s = Settings()

    # Mode 2: Explicit coordinate comparison if both coordinate pairs are provided
    if site_a_lat and site_a_lon and site_b_lat and site_b_lon:
        res_a = explain_heat_offset(site_a_lat, site_a_lon, tool_context=tool_context)
        res_b = explain_heat_offset(site_b_lat, site_b_lon, tool_context=tool_context)
        if res_a["status"] != "success":
            return res_a
        if res_b["status"] != "success":
            return res_b
        sa = res_a["data"]["site_assessment"]
        sb = res_b["data"]["site_assessment"]
        prov_combined = (res_a.get("provenance") or []) + (res_b.get("provenance") or [])
        return ToolResult(
            status="success",
            data={
                "comparison_mode": "coordinates",
                "site_a": {"label": site_a_label, **sa},
                "site_b": {"label": site_b_label, **sb},
                "deltas_a_minus_b": {
                    "predicted_offset_f": round(
                        float(sa["predicted_offset_f"]) - float(sb["predicted_offset_f"]), 2
                    ),
                    "expected_days_ge_95f_equiv": round(
                        float(sa["hot_days"]["expected_days_ge_95f_equiv"])
                        - float(sb["hot_days"]["expected_days_ge_95f_equiv"]),
                        1,
                    ),
                    "no_vehicle_rate": round(
                        float(sa["demographics"]["no_vehicle_rate"])
                        - float(sb["demographics"]["no_vehicle_rate"]),
                        4,
                    ),
                    "poverty_rate": round(
                        float(sa["demographics"]["poverty_rate"])
                        - float(sb["demographics"]["poverty_rate"]),
                        4,
                    ),
                    "share_65_plus": round(
                        float(sa["demographics"]["share_65_plus"])
                        - float(sb["demographics"]["share_65_plus"]),
                        4,
                    ),
                },
            },
            provenance=prov_combined,
            model_version=s.bqml_model_id,
        ).model_dump()

    # Mode 1: Rank-based comparison (`ranks=[1, 2, 3, 4]`)
    target_ranks = ranks or [1, 2, 3, 4]
    candidates = (
        tool_context.state.get("last_ranked_candidates") if tool_context is not None else None
    )
    prov_list: list[Any] = []
    if not candidates or len(candidates) < max(target_ranks):
        rank_res = rank_candidate_sites(k=3, unmeasured_only=False, tool_context=tool_context)
        if rank_res["status"] != "success":
            return rank_res
        prov_list = rank_res.get("provenance") or []
        candidates = (
            tool_context.state.get("last_ranked_candidates")
            if tool_context is not None
            else (rank_res["data"]["sites"] + rank_res["data"]["runner_up_sites"])
        )

    by_rank = {int(c["rank"]): c for c in (candidates or [])}
    compared = [by_rank[r] for r in target_ranks if r in by_rank]
    if len(compared) < 2:
        return ToolResult(
            status="not_found",
            error_message=f"Could not find at least 2 candidates matching ranks {target_ranks}.",
        ).model_dump()

    challenger = compared[-1]  # e.g., Site #4
    incumbents = compared[:-1]  # e.g., Sites #1, #2, #3

    displacement_deltas: list[dict[str, Any]] = []
    for inc in incumbents:
        displacement_deltas.append(
            {
                "incumbent_rank": inc["rank"],
                "incumbent_geo_id": inc["geo_id"],
                "incumbent_neighborhood": inc["neighborhood"],
                "challenger_rank": challenger["rank"],
                "challenger_geo_id": challenger["geo_id"],
                "challenger_neighborhood": challenger["neighborhood"],
                "challenger_spacing_conflict_with_rank": challenger.get(
                    "spacing_conflict_with_rank"
                ),
                "delta_priority_score_inc_minus_chal": round(
                    float(inc["priority_score"]) - float(challenger["priority_score"]), 3
                ),
                "delta_predicted_offset_f_inc_minus_chal": round(
                    float(inc["predicted_offset_f"]) - float(challenger["predicted_offset_f"]), 2
                ),
                "delta_no_vehicle_rate_inc_minus_chal": round(
                    float(inc["demographics"]["no_vehicle_rate"])
                    - float(challenger["demographics"]["no_vehicle_rate"]),
                    4,
                ),
                "delta_car_free_hh_inc_minus_chal": int(
                    inc["demographics"]["car_free_households"]
                )
                - int(challenger["demographics"]["car_free_households"]),
                "delta_poverty_rate_inc_minus_chal": round(
                    float(inc["demographics"]["poverty_rate"])
                    - float(challenger["demographics"]["poverty_rate"]),
                    4,
                ),
                "delta_share_65_plus_inc_minus_chal": round(
                    float(inc["demographics"]["share_65_plus"])
                    - float(challenger["demographics"]["share_65_plus"]),
                    4,
                ),
                "delta_pop_65_plus_inc_minus_chal": int(inc["demographics"]["pop_65_plus"])
                - int(challenger["demographics"]["pop_65_plus"]),
            }
        )

    return ToolResult(
        status="success",
        data={
            "comparison_mode": "ranks",
            "compared_ranks": [c["rank"] for c in compared],
            "compared_sites": compared,
            "challenger_site": challenger,
            "displacement_deltas": displacement_deltas,
        },
        provenance=prov_list,
        model_version=s.bqml_model_id,
    ).model_dump()
