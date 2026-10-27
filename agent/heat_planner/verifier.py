"""Deterministic GroundingVerifier & fallback template renderer (Stage 5)."""
from __future__ import annotations

import math
import re
from typing import Any

from .schemas import DataResult, VerificationReport

# Regex matching absolute forecast phrasing that violates Non-Negotiable #1
_BAD_ABSOLUTE_FORECAST_RE = re.compile(
    r"\b(?:it\s+will\s+be|will\s+reach|temperature\s+will\s+be|going\s+to\s+be)\s+\d{2,3}(?:\.\d+)?\s*°?\s*F\b",
    re.IGNORECASE,
)
_OFFSET_CONTEXT_RE = re.compile(
    r"\b(?:forecast|implies|implied|offset|above|below|relative\s+to|campaign\s+average|campaign\s+mean)\b",
    re.IGNORECASE,
)

# Regex matching citation tags like [P1], [P2]
_CITATION_TAG_RE = re.compile(r"\[P(\d+)\]")

# Regex matching explicit numeric claims in narrative (offsets, percentages, ratios, dollar figures)
_SIGNED_OFFSET_RE = re.compile(r"([+-]\d+\.\d+)\s*°\s*F")
_RATIO_RE = re.compile(r"\b(\d+\.\d+)x\b")
_DOLLAR_RE = re.compile(r"\$(\d{1,3}(?:,\d{3})+)")


def _collect_numbers_from_obj(obj: Any, out: set[float]) -> None:
    """Recursively collect all numeric values (and common scaled representations) from DataResult."""
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        val = float(obj)
        if math.isfinite(val):
            out.add(round(val, 4))
            out.add(round(val, 2))
            out.add(round(val, 1))
            out.add(round(val, 0))
            # If it's a rate in [0, 1], also add percentage (x100)
            if 0.0 <= abs(val) <= 1.0:
                pct = val * 100.0
                out.add(round(pct, 2))
                out.add(round(pct, 1))
                out.add(round(pct, 0))
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_numbers_from_obj(v, out)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _collect_numbers_from_obj(item, out)


def _matches_within_tolerance(val: float, allowed: set[float], tol: float = 0.15) -> bool:
    for a in allowed:
        if abs(val - a) <= tol:
            return True
    return False


def render_deterministic_fallback(data_result: DataResult) -> str:
    """Render a 100% grounded, citation-tagged markdown summary directly from DataResult."""
    cite = f"[{data_result.provenance[0].provenance_id}]" if data_result.provenance else "[P1]"

    if data_result.status in ("out_of_scope", "refused", "needs_clarification", "no_data", "error"):
        return (
            f"**Scope & Boundary Notice ({data_result.status}):** "
            f"{data_result.error_message or 'Request outside model support.'} {cite}"
        )

    if data_result.recommendation is not None:
        return data_result.recommendation.proposal_markdown

    lines: list[str] = []
    if data_result.sites:
        s0 = data_result.sites[0]
        if len(data_result.sites) == 1 and data_result.intent_type == "explain_location":
            top_d = s0.drivers[0] if s0.drivers else None
            drv_str = (
                f"`{top_d.feature}` ({top_d.attribution:+.3f} °F)"
                if top_d
                else "built-environment density"
            )
            implied_clause = (
                f"; on a `{s0.forecast_high_f:.0f} °F` forecast day, that implies conditions feeling closer to `~{s0.forecast_implied_f:.1f} °F`"
                if s0.forecast_high_f and s0.forecast_implied_f
                else ""
            )
            lines.append(
                f"### Street-Level Heat Offset Assessment — {s0.neighborhood} (Tract `{s0.geo_id}`) {cite}\n\n"
                f"- **Coordinates:** `{s0.lat:.4f}, {s0.lon:.4f}` (`{'unmeasured' if s0.unmeasured else 'measured'}` grid cell) · "
                f"[Google Maps Pin]({s0.google_maps_url}) · [Walking Directions]({s0.google_maps_walking_url}) {cite}\n"
                f"- **Predicted Heat Offset (`a4i_ml.offset_model_v1`):** **`{s0.predicted_offset_f:+.2f} °F`** relative to the Atlanta Heat Watch campaign mean (`{s0.campaign_mean_f:.1f} °F`){implied_clause} {cite}\n"
                f"- **Top `ML.EXPLAIN_PREDICT` Physical Driver:** {drv_str} {cite}\n"
                f"- **GHCN Heat Frequency (`2019–2025`):** `~{s0.hot_days.expected_days_ge_95f_equiv:.1f}` days/yr of `>=95 °F`-equivalent heat vs. `{s0.hot_days.city_days_ge_95f_per_yr:.1f}` days/yr citywide (`+{s0.hot_days.extra_days_ge_95f_equiv:.1f}` extra hot days/yr) {cite}\n"
                f"- **Walkable Catchment (`{s0.demographics.radius_m:.0f} m`):** `{s0.demographics.total_pop:,}` residents, `{s0.demographics.car_free_households:,}` car-free households (`{s0.demographics.no_vehicle_rate*100:.1f}%`), `{s0.demographics.pop_65_plus:,}` seniors 65+ (`{s0.demographics.share_65_plus*100:.1f}%`), `{s0.demographics.poverty_rate*100:.1f}%` poverty {cite}"
            )
        else:
            lines.append(
                f"### Ranked Cooling-Center Sites — Atlanta, GA (`2,000 m` Minimum Spacing) {cite}\n"
            )
            for s in data_result.sites:
                top_d = s.drivers[0] if s.drivers else None
                drv_str = (
                    f"`{top_d.feature}` ({top_d.attribution:+.3f} °F)" if top_d else "n/a"
                )
                lines.append(
                    f"- **Site #{s.rank} — {s.neighborhood} (`{s.point_id}`, Tract `{s.geo_id}`):** "
                    f"Predicted **`{s.predicted_offset_f:+.2f} °F`** hotter than the Atlanta campaign mean (`82.1 °F`), "
                    f"priority score **`{s.priority_score:.3f}`**, top driver {drv_str}, "
                    f"`{s.demographics.no_vehicle_rate*100:.1f}%` car-free households (`{s.demographics.car_free_households:,}` HH), "
                    f"`{s.demographics.poverty_rate*100:.1f}%` poverty, `{s.demographics.share_65_plus*100:.1f}%` seniors 65+ "
                    f"([Map Pin]({s.google_maps_url})) {cite}"
                )

    if data_result.comparison_table:
        lines.append(f"\n### Candidate Site Comparison & Displacement Trade-Offs {cite}\n")
        for row in data_result.comparison_table:
            if "incumbent_rank" in row:
                lines.append(
                    f"- **Site #{row['incumbent_rank']} ({row['incumbent_neighborhood']}, Tract `{row['incumbent_geo_id']}`) "
                    f"vs. Challenger Site #{row['challenger_rank']} ({row['challenger_neighborhood']}, Tract `{row['challenger_geo_id']}`):** "
                    f"Priority score delta `{row['delta_priority_score_inc_minus_chal']:+.3f}`, "
                    f"predicted offset delta `{row['delta_predicted_offset_f_inc_minus_chal']:+.2f} °F`, "
                    f"no-vehicle rate delta `{row['delta_no_vehicle_rate_inc_minus_chal']*100:+.1f} pp` "
                    f"(`{row['delta_car_free_hh_inc_minus_chal']:+,}` car-free HH), "
                    f"poverty rate delta `{row['delta_poverty_rate_inc_minus_chal']*100:+.1f} pp`, "
                    f"seniors 65+ share delta `{row['delta_share_65_plus_inc_minus_chal']*100:+.1f} pp` {cite}"
                )

    if data_result.heat_frequency is not None:
        hf = data_result.heat_frequency
        lines.append(
            f"\n### NOAA GHCN Station Heat Frequency (`{hf.years_covered}`, `{hf.full_years_count}` Full Years) {cite}\n\n"
            f"- **Citywide Average Hot Days/Yr:** `{hf.avg_days_ge_90f:.1f}` days/yr `>=90 °F`, "
            f"**`{hf.avg_days_ge_95f:.1f}` days/yr `>=95 °F`**, `{hf.avg_days_ge_100f:.1f}` days/yr `>=100 °F` "
            f"(peak recorded station max `{hf.hottest_temp_recorded_f:.1f} °F`) {cite}"
        )

    if data_result.equity_audit is not None:
        lines.append(
            f"\n### Post-Hoc Equity Audit (`a4i_semantic.tract_features` + `tract_audit_race`) {cite}\n\n"
            f"{data_result.equity_audit.summary} {cite}"
        )

    return "\n".join(lines).strip() or f"Completed `{data_result.intent_type}` analysis for Atlanta, GA. {cite}"


def verify_narrative(
    draft_narrative: str,
    data_result: DataResult,
) -> tuple[str, VerificationReport]:
    """Verify numeric grounding, offset framing, and `[Pn]` citations on `draft_narrative`.

    If any check fails, returns the deterministic fallback summary rendered from `data_result`
    and sets `fallback_used=True`.
    """
    text = (draft_narrative or "").strip()
    if not text:
        fallback = render_deterministic_fallback(data_result)
        return fallback, VerificationReport(
            passed=False,
            ungrounded_numbers=[],
            framing_violations=["Empty narrative draft."],
            missing_citations=[],
            fallback_used=True,
        )

    allowed_numbers: set[float] = {
        82.1,
        23.9,
        78.0,
        1.6,
        104.0,
        350.0,
        2000.0,
        800.0,
        1000.0,
        150.0,
        250.0,
        65.0,
        90.0,
        95.0,
        100.0,
        0.677,
        0.72,
        1.07,
    }
    _collect_numbers_from_obj(data_result.model_dump(), allowed_numbers)

    ungrounded: list[str] = []
    # Check signed offsets (+1.28°F)
    for m in _SIGNED_OFFSET_RE.finditer(text):
        val = float(m.group(1))
        if not _matches_within_tolerance(val, allowed_numbers, tol=0.15):
            ungrounded.append(m.group(0))

    # Check ratios (6.12x)
    for m in _RATIO_RE.finditer(text):
        val = float(m.group(1))
        if not _matches_within_tolerance(val, allowed_numbers, tol=0.15):
            ungrounded.append(m.group(0))

    # Check dollar figures ($17,843)
    for m in _DOLLAR_RE.finditer(text):
        val = float(m.group(1).replace(",", ""))
        if not _matches_within_tolerance(val, allowed_numbers, tol=50.0):
            ungrounded.append(m.group(0))

    # Check offset framing (Non-Negotiable #1)
    framing_violations: list[str] = []
    for m in _BAD_ABSOLUTE_FORECAST_RE.finditer(text):
        # Check surrounding window for forecast/implies/offset framing
        start = max(0, m.start() - 100)
        end = min(len(text), m.end() + 100)
        window = text[start:end]
        if not _OFFSET_CONTEXT_RE.search(window):
            framing_violations.append(m.group(0))

    # Check citation tags [Pn] when provenance exists
    missing_citations: list[str] = []
    valid_prov_ids = {p.provenance_id for p in data_result.provenance}
    found_tags = {f"P{m.group(1)}" for m in _CITATION_TAG_RE.finditer(text)}
    if valid_prov_ids:
        if not found_tags:
            missing_citations.append("No [Pn] provenance citation tags found in narrative.")
        else:
            invalid_tags = found_tags - valid_prov_ids
            if invalid_tags:
                missing_citations.append(
                    f"Referenced unknown provenance IDs: {sorted(invalid_tags)}"
                )

    passed = not (ungrounded or framing_violations or missing_citations)
    if not passed:
        fallback = render_deterministic_fallback(data_result)
        return fallback, VerificationReport(
            passed=False,
            ungrounded_numbers=ungrounded,
            framing_violations=framing_violations,
            missing_citations=missing_citations,
            fallback_used=True,
        )

    return text, VerificationReport(
        passed=True,
        ungrounded_numbers=[],
        framing_violations=[],
        missing_citations=[],
        fallback_used=False,
    )
