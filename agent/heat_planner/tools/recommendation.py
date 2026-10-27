"""Assemble the validated PlacementRecommendation artifact & council-ready proposal."""
from __future__ import annotations

import logging
from typing import Any

from google.adk.tools import ToolContext

from ..config import Settings
from ..schemas import (
    CityHeatFrequencySummary,
    EquityAudit,
    PlacementRecommendation,
    Provenance,
    SiteAssessment,
    ToolResult,
)
from .audit import run_equity_audit
from .heat_model import rank_candidate_sites
from .history import get_heat_frequency

log = logging.getLogger(__name__)

LIMITATIONS: list[str] = [
    "Single-day heat snapshot: Heat Watch captures relative spatial patterns from one afternoon traverse campaign; it cannot predict absolute temperature on a future date.",
    "Linear spatial-block generalization (R² = 0.677, MAE = 0.72°F vs. 1.07°F baseline): Linear built-environment features explain ~68% of spatial offset variance; micro-scale shade, building heights, and wind canyons are not resolved.",
    "Tract-level demographic resolution: ACS 2020 5-year estimates reflect census-tract averages (~1,200–8,000 residents), not individual blocks or buildings.",
    "7-year station window (2019–2025): GHCN heat-frequency averages (23.9 days/yr >=95°F citywide) span 7 full years, capturing interannual variability rather than a 30-year WMO climatology.",
    "Observational associations, not causal simulations: ML.EXPLAIN_PREDICT attributions explain why a location is predicted hotter, not the causal cooling effect of planting trees or installing cool roofs.",
    "Walkable siting requires parcel & facility verification: Coordinates identify priority 250 m grid cells and tracts; final capital siting requires checking city-owned parcel availability, ADA sidewalk condition, and transit access.",
]


def _format_council_memo(
    city: str,
    track: str,
    intervention: str,
    model_version: str,
    campaign_mean_f: float,
    heat_freq: CityHeatFrequencySummary,
    sites: list[SiteAssessment],
    runner_up_sites: list[SiteAssessment],
    audit: EquityAudit,
    limitations: list[str],
    citation_tag: str = "[P1]",
) -> str:
    lines: list[str] = [
        f"# Placement Recommendation — {city}, GA ({intervention})",
        "",
        f"**Track:** `{track}` (*This budget cycle — capital siting & walkability*) · "
        f"**BQML Model:** `a4i_ml.{model_version}` (`LINEAR_REG` on spatial-block split) · "
        f"**Campaign Reference Mean:** `{campaign_mean_f:.1f} °F` · "
        f"**City Baseline Hot Days (`>=95°F`):** `{heat_freq.avg_days_ge_95f:.1f} days/yr` "
        f"(GHCN `{heat_freq.years_covered}`) {citation_tag}",
        "",
        "## 1. Ranked Candidate Sites (2,000 m Minimum Spacing, One Per Census Tract)",
        "",
        "| Rank | Neighborhood & Tract | Coordinates (`lat, lon`) | Predicted Offset (`°F` vs. City Mean) | Expected `>=95°F`-Equiv Days/Yr | Top `ML.EXPLAIN_PREDICT` Driver | Who Lives Here (800 m Catchment / Tract) | Walkable Access Link |",
        "|---:|---|---|---:|---:|---|---|---|",
    ]
    for s in sites:
        top_d = s.drivers[0] if s.drivers else None
        driver_str = (
            f"`{top_d.feature}` ({top_d.attribution:+.3f} °F)" if top_d else "n/a"
        )
        dem = s.demographics
        who_str = (
            f"Pop {dem.total_pop:,} · {dem.car_free_households:,} car-free HH "
            f"({dem.no_vehicle_rate*100:.1f}%) · {dem.pop_65_plus:,} seniors 65+ "
            f"({dem.share_65_plus*100:.1f}%) · {dem.poverty_rate*100:.1f}% poverty"
        )
        exp_days_str = (
            f"**{s.hot_days.expected_days_ge_95f_equiv:.1f}** "
            f"(+{s.hot_days.extra_days_ge_95f_equiv:.1f} vs. {s.hot_days.city_days_ge_95f_per_yr:.1f} city)"
        )
        map_link = (
            f"[Map Pin]({s.google_maps_url}) · [Walk Dir]({s.google_maps_walking_url})"
            if s.google_maps_url
            else f"`{s.lat:.4f}, {s.lon:.4f}`"
        )
        implied_note = (
            f" (~{s.forecast_implied_f:.1f} °F on {s.forecast_high_f:.0f} °F forecast)"
            if s.forecast_implied_f is not None and s.forecast_high_f is not None
            else ""
        )
        lines.append(
            f"| **#{s.rank}** | **{s.neighborhood}** (`{s.geo_id}`) | `{s.lat:.4f}, {s.lon:.4f}` "
            f"({'unmeasured' if s.unmeasured else 'measured'}) | **{s.predicted_offset_f:+.2f} °F**{implied_note} | "
            f"{exp_days_str} | {driver_str} | {who_str} | {map_link} |"
        )

    lines.extend(["", "## 2. Site-by-Site Rationale", ""])
    for s in sites:
        drv_list = ", ".join(
            f"`{d.feature}` ({d.attribution:+.3f} °F)" for d in s.drivers[:3]
        )
        lines.append(
            f"- **Site #{s.rank} — {s.neighborhood} (`{s.point_id}`, Tract `{s.geo_id}`, "
            f"Priority Score `{s.priority_score:.3f}`):** {s.why_here} "
            f"Top BQML attributions: {drv_list}. {citation_tag}"
        )

    if runner_up_sites:
        r4 = runner_up_sites[0]
        conflict_note = (
            f" (within 2,000 m spacing buffer of Site #{r4.spacing_conflict_with_rank})"
            if r4.spacing_conflict_with_rank
            else ""
        )
        lines.extend(
            [
                "",
                f"**Runner-up Site #{r4.rank}:** **{r4.neighborhood}** (`{r4.point_id}`, Tract `{r4.geo_id}`){conflict_note} "
                f"— predicted `{r4.predicted_offset_f:+.2f} °F` offset, priority score `{r4.priority_score:.3f}`, "
                f"`{r4.demographics.no_vehicle_rate*100:.1f}%` car-free households, "
                f"`{r4.demographics.poverty_rate*100:.1f}%` poverty. {citation_tag}",
            ]
        )

    by_m = {m.metric: m for m in audit.metrics}
    nv = by_m.get("2_no_vehicle_rate")
    pov = by_m.get("1_poverty_rate")
    s65 = by_m.get("3_share_65_plus")
    inc = by_m.get("4_median_income_usd")

    lines.extend(
        [
            "",
            "## 3. Post-Hoc Equity Audit (Recommended Tracts vs. Atlanta City Baseline)",
            "",
            "| Metric | Recommended Tracts | Atlanta City Baseline (350 Populated Tracts) | Ratio (Rec / City) |",
            "|---|---:|---:|---:|",
        ]
    )
    if nv:
        lines.append(
            f"| **No-Vehicle Households (`2_no_vehicle_rate`)** | {nv.recommended_sites*100:.2f}% | "
            f"{nv.city_overall*100:.2f}% | **{nv.ratio_rec_to_city:.2f}x** |"
        )
    if pov:
        lines.append(
            f"| **Poverty Rate (`1_poverty_rate`)** | {pov.recommended_sites*100:.2f}% | "
            f"{pov.city_overall*100:.2f}% | **{pov.ratio_rec_to_city:.2f}x** |"
        )
    if s65:
        lines.append(
            f"| **Seniors Aged 65+ (`3_share_65_plus`)** | {s65.recommended_sites*100:.2f}% | "
            f"{s65.city_overall*100:.2f}% | **{s65.ratio_rec_to_city:.2f}x** |"
        )
    if inc:
        lines.append(
            f"| **Median Household Income (`4_median_income_usd`)** | ${int(round(inc.recommended_sites)):,} | "
            f"${int(round(inc.city_overall)):,} | **{inc.ratio_rec_to_city:.2f}x** |"
        )

    lines.extend(["", f"{audit.summary} {citation_tag}", "", "## 4. Known Limitations & Operational Next Steps", ""])
    for lim in limitations:
        lines.append(f"- {lim}")

    return "\n".join(lines)


def assemble_placement_recommendation(
    intervention: str = "3 permanent walkable cooling centers (This budget cycle)",
    k: int = 3,
    forecast_high_f: float = 0.0,
    unmeasured_only: bool = False,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Assemble the complete, schema-validated PlacementRecommendation artifact.

    Combines the top `k` ranked candidate sites from `rank_candidate_sites`, multi-year
    GHCN station heat frequency (`get_heat_frequency`), the post-hoc equity audit
    (`run_equity_audit`), honest limitations, and a council-ready markdown proposal.

    Args:
        intervention: Description of the capital / operational intervention being sited.
        k: Number of sites to include in the recommendation (default 3).
        forecast_high_f: Optional NWS forecast high in °F (e.g. 98.0) to compute implied site feel.
        unmeasured_only: Whether to restrict candidate pool to unmeasured grid cells only.
    """
    s = Settings()
    k = max(1, min(int(k), 10))
    prov_list: list[Provenance] = []

    rank_res = rank_candidate_sites(
        k=k,
        unmeasured_only=bool(unmeasured_only),
        forecast_high_f=float(forecast_high_f),
        tool_context=tool_context,
    )
    if rank_res["status"] != "success":
        return rank_res
    prov_list.extend(
        Provenance.model_validate(p) if isinstance(p, dict) else p
        for p in (rank_res.get("provenance") or [])
    )

    sites = [SiteAssessment.model_validate(item) for item in rank_res["data"]["sites"][:k]]
    runner_ups = [
        SiteAssessment.model_validate(item)
        for item in (rank_res["data"].get("runner_up_sites") or [])
    ]
    geo_ids = [site.geo_id for site in sites]

    audit_res = run_equity_audit(site_geo_ids=geo_ids, tool_context=tool_context)
    if audit_res["status"] != "success":
        return audit_res
    prov_list.extend(
        Provenance.model_validate(p) if isinstance(p, dict) else p
        for p in (audit_res.get("provenance") or [])
    )
    audit = EquityAudit.model_validate(audit_res["data"])

    top_offset = sites[0].predicted_offset_f if sites else 0.0
    freq_res = get_heat_frequency(
        threshold_f=95.0, offset_f=top_offset, tool_context=tool_context
    )
    if freq_res["status"] != "success":
        return freq_res
    prov_list.extend(
        Provenance.model_validate(p) if isinstance(p, dict) else p
        for p in (freq_res.get("provenance") or [])
    )
    freq_data = freq_res["data"]
    heat_freq = CityHeatFrequencySummary(
        years_covered=str(freq_data["years_covered"]),
        full_years_count=int(freq_data["full_years_count"]),
        avg_days_ge_90f=float(freq_data["avg_days_ge_90f"]),
        avg_days_ge_95f=float(freq_data["avg_days_ge_95f"]),
        avg_days_ge_100f=float(freq_data["avg_days_ge_100f"]),
        hottest_temp_recorded_f=float(freq_data["hottest_temp_recorded_f"]),
        trend_days_per_decade=(
            float(freq_data["trend_days_per_decade"])
            if freq_data.get("trend_days_per_decade") is not None
            else None
        ),
        by_year=list(freq_data.get("by_year") or []),
    )

    # Re-number provenance IDs sequentially P1..Pn
    for idx_p, p in enumerate(prov_list, start=1):
        p.provenance_id = f"P{idx_p}"

    memo = _format_council_memo(
        city=s.city,
        track=s.track,
        intervention=intervention,
        model_version=s.bqml_model_id,
        campaign_mean_f=82.1,
        heat_freq=heat_freq,
        sites=sites,
        runner_up_sites=runner_ups,
        audit=audit,
        limitations=LIMITATIONS,
        citation_tag="[P1]",
    )

    rec = PlacementRecommendation(
        city=s.city,
        track=s.track,  # type: ignore[arg-type]
        intervention=intervention,
        model_version=s.bqml_model_id,
        campaign_mean_f=82.1,
        sites=sites,
        runner_up_sites=runner_ups,
        heat_frequency=heat_freq,
        equity_audit=audit,
        proposal_markdown=memo,
        limitations=LIMITATIONS,
    )

    payload = rec.model_dump()
    if tool_context is not None:
        tool_context.state["last_recommendation"] = payload

    return ToolResult(
        status="success",
        data=payload,
        provenance=prov_list,
        model_version=s.bqml_model_id,
    ).model_dump()
