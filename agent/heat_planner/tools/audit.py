"""Post-hoc equity audit tool comparing recommended tracts against the Atlanta city baseline via MCP Toolbox."""
from __future__ import annotations

import logging
from typing import Any

from google.adk.tools import ToolContext

from ..config import Settings
from ..mcp_client import invoke_mcp_tool
from ..schemas import EquityAudit, EquityAuditMetricRow, Provenance, ToolResult
from .heat_model import rank_candidate_sites

log = logging.getLogger(__name__)


def run_equity_audit(
    site_geo_ids: list[str] | None = None,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Run the post-hoc equity audit comparing recommended census tracts against the
    population-weighted Atlanta city baseline (350 populated tracts).

    Calls MCP `equity_audit(geo_id_1, geo_id_2, geo_id_3)` over `a4i_semantic.tract_features`
    and `a4i_semantic.tract_audit_race`. Race/ethnicity columns appear ONLY here as a
    post-hoc output check — never in the BQML heat model or ranking score.

    Args:
        site_geo_ids: Optional list of 11-character census tract GEOIDs to audit.
            If omitted, uses the tracts from the most recent `rank_candidate_sites` call.
    """
    s = Settings()
    geo_ids = [str(g).zfill(11) for g in (site_geo_ids or []) if g]
    if not geo_ids and tool_context is not None:
        ranked = tool_context.state.get("last_ranked_sites") or []
        geo_ids = [str(site["geo_id"]).zfill(11) for site in ranked if site.get("geo_id")]

    prov_list: list[Provenance] = []
    if not geo_ids:
        rank_res = rank_candidate_sites(k=3, unmeasured_only=False, tool_context=tool_context)
        if rank_res["status"] != "success":
            return rank_res
        prov_list.extend(
            Provenance.model_validate(p) if isinstance(p, dict) else p
            for p in (rank_res.get("provenance") or [])
        )
        geo_ids = [
            str(site["geo_id"]).zfill(11)
            for site in (rank_res["data"].get("sites") or [])
            if site.get("geo_id")
        ]

    unique_geo_ids = list(dict.fromkeys(geo_ids))
    if not unique_geo_ids:
        return ToolResult(
            status="not_found",
            error_message="No census tract geo_ids available to audit.",
        ).model_dump()

    g1 = unique_geo_ids[0]
    g2 = unique_geo_ids[1] if len(unique_geo_ids) > 1 else g1
    g3 = unique_geo_ids[2] if len(unique_geo_ids) > 2 else g2

    try:
        rows, _ = invoke_mcp_tool(
            "equity_audit",
            tool_name="run_equity_audit",
            provenance_list=prov_list,
            geo_id_1=g1,
            geo_id_2=g2,
            geo_id_3=g3,
        )
    except Exception as exc:
        log.exception("run_equity_audit failed")
        return ToolResult(status="error", error_message=str(exc)).model_dump()

    if not rows:
        return ToolResult(
            status="not_found",
            error_message=f"Could not match tract GEOIDs {unique_geo_ids} in a4i_semantic.tract_features.",
            provenance=prov_list,
        ).model_dump()

    metric_rows: list[EquityAuditMetricRow] = []
    by_metric: dict[str, EquityAuditMetricRow] = {}
    for r in rows:
        rec_val = float(
            r["recommended_sites"]
            if r.get("recommended_sites") is not None
            else r.get("sites_value", 0.0)
        )
        city_val = float(
            r["city_overall"]
            if r.get("city_overall") is not None
            else r.get("city_value", 0.0)
        )
        ratio_val = (
            float(r["ratio_rec_to_city"])
            if r.get("ratio_rec_to_city") is not None
            else (float(r["ratio"]) if r.get("ratio") is not None else None)
        )
        m_row = EquityAuditMetricRow(
            metric=str(r["metric"]),
            recommended_sites=rec_val,
            city_overall=city_val,
            ratio_rec_to_city=ratio_val,
        )
        metric_rows.append(m_row)
        by_metric[m_row.metric] = m_row

    def _rec(m: str) -> float:
        return by_metric[m].recommended_sites if m in by_metric else 0.0

    def _city(m: str) -> float:
        return by_metric[m].city_overall if m in by_metric else 0.0

    def _ratio(m: str) -> float:
        if m in by_metric and by_metric[m].ratio_rec_to_city is not None:
            return float(by_metric[m].ratio_rec_to_city or 0.0)
        c_val = _city(m)
        return round(_rec(m) / c_val, 2) if c_val else 0.0

    ratios = {
        "no_vehicle_rate": _ratio("2_no_vehicle_rate"),
        "poverty_rate": _ratio("1_poverty_rate"),
        "share_65_plus": _ratio("3_share_65_plus"),
        "median_income_usd": _ratio("4_median_income_usd"),
    }
    deltas = {
        "poverty_rate": round(_rec("1_poverty_rate") - _city("1_poverty_rate"), 4),
        "no_vehicle_rate": round(_rec("2_no_vehicle_rate") - _city("2_no_vehicle_rate"), 4),
        "share_65_plus": round(_rec("3_share_65_plus") - _city("3_share_65_plus"), 4),
        "median_income_usd": round(_rec("4_median_income_usd") - _city("4_median_income_usd"), 0),
        "median_age_years": round(_rec("5_median_age_years") - _city("5_median_age_years"), 1),
    }
    passes = deltas["poverty_rate"] >= 0.0 and deltas["no_vehicle_rate"] >= 0.0

    rec_nv_pct = _rec("2_no_vehicle_rate") * 100
    city_nv_pct = _city("2_no_vehicle_rate") * 100
    rec_pov_pct = _rec("1_poverty_rate") * 100
    city_pov_pct = _city("1_poverty_rate") * 100
    rec_65_pct = _rec("3_share_65_plus") * 100
    city_65_pct = _city("3_share_65_plus") * 100
    rec_inc = int(round(_rec("4_median_income_usd")))
    city_inc = int(round(_city("4_median_income_usd")))

    summary = (
        f"Across the {len(unique_geo_ids)} recommended {s.city} tracts ({', '.join(unique_geo_ids)}), "
        f"households without a vehicle are {rec_nv_pct:.2f}% vs. {city_nv_pct:.2f}% citywide "
        f"({ratios['no_vehicle_rate']:.2f}x ratio, {deltas['no_vehicle_rate']*100:+.2f} pp), "
        f"poverty is {rec_pov_pct:.2f}% vs. {city_pov_pct:.2f}% citywide "
        f"({ratios['poverty_rate']:.2f}x ratio, {deltas['poverty_rate']*100:+.2f} pp), "
        f"seniors aged 65+ are {rec_65_pct:.2f}% vs. {city_65_pct:.2f}% citywide "
        f"({ratios['share_65_plus']:.2f}x ratio, {deltas['share_65_plus']*100:+.2f} pp), and "
        f"household-weighted median income is ${rec_inc:,} vs. ${city_inc:,} citywide "
        f"({ratios['median_income_usd']:.2f}x ratio)."
    )

    audit = EquityAudit(
        site_geo_ids=unique_geo_ids,
        metrics=metric_rows,
        ratios=ratios,
        deltas=deltas,
        passes_equity_check=passes,
        summary=summary,
    )

    payload = audit.model_dump()
    if tool_context is not None:
        tool_context.state["last_equity_audit"] = payload
        existing_prov = list(tool_context.state.get("turn_provenance") or [])
        existing_prov.extend(p.model_dump() for p in prov_list)
        tool_context.state["turn_provenance"] = existing_prov

    return ToolResult(
        status="success",
        data=payload,
        provenance=prov_list,
        model_version=s.bqml_model_id,
        caveats=[
            "Race/ethnicity shares (7_posthoc_black_resident_share, 8_posthoc_white_resident_share, 9_posthoc_hispanic_resident_share) are computed strictly post-hoc on output tracts from a4i_semantic.tract_audit_race and never enter the BQML model or ranking weights.",
        ],
    ).model_dump()
