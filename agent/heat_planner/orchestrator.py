"""5-Stage HeatPlannerOrchestrator pipeline (Intent -> Gate -> MCP Router -> Writer -> Verifier)."""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from .config import Settings
from .schemas import (
     AgentApiResponse,
    CityHeatFrequencySummary,
    DataRequest,
    DataResult,
    EquityAudit,
    Intent,
    PlacementRecommendation,
    Provenance,
    SiteAssessment,
)
from .tools.audit import run_equity_audit
from .tools.demographics import get_area_demographics
from .tools.heat_model import compare_sites, explain_heat_offset, rank_candidate_sites
from .tools.history import get_heat_frequency
from .tools.location import _CURATED_PLACES, resolve_location
from .tools.recommendation import assemble_placement_recommendation
from .verifier import render_deterministic_fallback, verify_narrative

log = logging.getLogger(__name__)

_COORD_EXTRACT_RE = re.compile(
    r"(?P<lat>3[234]\.\d{2,6})\s*[,\s]\s*(?P<lon>-8[345]\.\d{2,6})"
)
_FORECAST_EXTRACT_RE = re.compile(r"(\d{2,3}(?:\.\d+)?)\s*°?\s*F\s+forecast", re.IGNORECASE)
_RANK_EXTRACT_RE = re.compile(r"(?:site|rank|#)\s*(\d+)", re.IGNORECASE)

_NON_TARGET_CITIES = (
    "phoenix",
    "miami",
    "dallas",
    "houston",
    "chicago",
    "new york",
    "los angeles",
    "seattle",
    "boston",
    "denver",
    "savannah",
    "alpharetta",
    "marietta",
    "roswell",
    "peachtree city",
)


class _SessionContextAdapter:
    """Lightweight adapter providing `.state` dict compatible with ADK `ToolContext`."""

    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state


def classify_intent(message: str, session_state: dict[str, Any] | None = None) -> Intent:
    """Stage 1: Parse the planner prompt into a strict `Intent` contract."""
    s = Settings()
    raw = (message or "").strip()
    lower = raw.lower()

    # 1. Check ambiguous / under-specified prompt ("Make it cooler", "Help", "Fix heat", "Can you help me with heat?")
    if len(raw.split()) <= 7 and any(
        w in lower
        for w in ("make it cooler", "cool it down", "fix the heat", "help", "what now")
    ) and not any(
        w in lower
        for w in ("atlanta", "cooling center", "offset", "ghcn", "venetian", "west end", "mechanicsville")
    ):
        return Intent(
            intent_type="ambiguous_prompt",
            city=s.city,
            missing_fields=["intent_type", "location_or_siting_goal"],
            clarification_question=(
                f"To help plan {s.city}'s heat response, could you clarify whether you want to: "
                "(1) rank the top 3 walkable cooling-center sites across Atlanta for the upcoming "
                "City Council budget vote, (2) inspect the predicted heat offset and physical drivers "
                "at a specific neighborhood or coordinate (e.g., Venetian Hills, West End, Vine City), "
                "or (3) review multi-year NOAA GHCN hot-day frequency (2019–2025)?"
            ),
        )

    # 2. Check race/ethnicity in model or ranking weights refusal
    if any(
        phrase in lower
        for phrase in (
            "by race",
            "percent black",
            "black share",
            "black population share",
            "race as a feature",
            "race as a model",
            "hispanic share",
            "white share",
            "racial",
            "ethnicity as a feature",
            "weight by race",
            "rank by race",
            "re-rank by black",
            "rerank by black",
        )
    ):
        return Intent(
            intent_type="race_in_model",
            city=s.city,
            refusal_reason=(
                "Race and ethnicity are strictly excluded from our BigQuery ML heat-offset model "
                f"(`a4i_ml.{s.bqml_model_id}`) and from the candidate site ranking formula by design "
                "(Challenge Non-Negotiable #4). Siting uses physical heat offset plus walkability "
                "and socioeconomic/age vulnerability (`no_vehicle_rate`, `poverty_rate`, `share_65_plus`). "
                "Racial composition (`a4i_semantic.tract_audit_race`) is evaluated strictly post-hoc "
                "in the equity audit of already-selected sites."
            ),
        )

    # 3. Check causal intervention simulation refusal ("plant 500 trees", "cool roofs", "what if we plant")
    if any(
        phrase in lower
        for phrase in (
            "plant ",
            "planting ",
            "trees",
            "cool roof",
            "white roof",
            "paint roof",
            "reflective pavement",
            "how many degrees would it cool",
            "how much will it cool",
            "simulate cooling",
        )
    ) and any(
        w in lower
        for w in ("if we", "what if", "would it cool", "will it cool", "reduce temperature", "drop")
    ):
        return Intent(
            intent_type="causal_simulation",
            city=s.city,
            refusal_reason=(
                f"Our BigQuery ML model (`a4i_ml.{s.bqml_model_id}`) is a cross-sectional observational "
                "regression (`ML.EXPLAIN_PREDICT`) trained on existing built-environment features to "
                "predict spatial heat offsets (`°F` relative to the Atlanta campaign mean). It is not "
                "a causal or radiative microclimate simulator and cannot estimate how many degrees "
                "planting trees or installing cool roofs would cool a block. I can instead show this "
                "location's current predicted heat offset and its top physical drivers."
            ),
        )

    # 4. Check future weather forecast refusal ("next Tuesday at 3pm", "tomorrow's temperature")
    if any(
        phrase in lower
        for phrase in (
            "next tuesday",
            "next wednesday",
            "next week",
            "tomorrow",
            "at 3pm",
            "at 3 pm",
            "weather forecast for",
            "what will the temperature be on",
        )
    ):
        return Intent(
            intent_type="future_forecast",
            city=s.city,
            refusal_reason=(
                "This planning assistant models time-invariant spatial heat offsets (`°F` above or below "
                "Atlanta's 82.1°F Heat Watch campaign mean) and historical annual hot-day frequencies "
                "from NOAA GHCN weather stations (2019–2025). It does not produce date- or hour-specific "
                "weather forecasts; please consult the National Weather Service (NWS) for forecasts."
            ),
        )

    # 5. Check out-of-scope city / suburb
    for bad_city in _NON_TARGET_CITIES:
        if re.search(rf"\b{re.escape(bad_city)}\b", lower):
            return Intent(
                intent_type="out_of_scope_city",
                city=bad_city.title(),
                location_query=bad_city.title(),
                refusal_reason=(
                    f"'{bad_city.title()}' lies outside the {s.city}, GA Heat Watch campaign footprint. "
                    f"Our BigQuery ML model (`a4i_ml.{s.bqml_model_id}`) has training support only inside "
                    f"{s.city}'s 1 km-buffered Heat Watch campaign boundary and refuses to extrapolate "
                    "to other cities or outer suburbs."
                ),
            )

    # Extract optional forecast high (e.g. "98°F forecast")
    forecast_high_f: float | None = None
    m_fc = _FORECAST_EXTRACT_RE.search(raw)
    if m_fc:
        forecast_high_f = float(m_fc.group(1))

    # Extract coordinates if present
    lat: float | None = None
    lon: float | None = None
    m_coord = _COORD_EXTRACT_RE.search(raw)
    if m_coord:
        lat = float(m_coord.group("lat"))
        lon = float(m_coord.group("lon"))

    # Extract named neighborhood if present
    loc_query: str | None = None
    for place_key in _CURATED_PLACES:
        if re.search(rf"\b{re.escape(place_key)}\b", lower):
            loc_query = place_key
            break

    # 6. Check compare_sites ("Why not Site #4", "compare site", "runner-up", "vs site")
    if any(
        phrase in lower
        for phrase in (
            "site #4",
            "site 4",
            "rank 4",
            "#4",
            "runner-up",
            "runner up",
            "compare site",
            "why not site",
            "instead of site",
            "displace",
        )
    ):
        found_ranks = [int(x) for x in _RANK_EXTRACT_RE.findall(raw) if 1 <= int(x) <= 10]
        if not found_ranks or found_ranks == [4]:
            compared_ranks = [1, 2, 3, 4]
        else:
            compared_ranks = sorted(set([1, 2, 3] + found_ranks))
        return Intent(
            intent_type="compare_sites",
            city=s.city,
            compared_ranks=compared_ranks,
            forecast_high_f=forecast_high_f,
        )

    # 7. Check heat_frequency ("how often", "getting worse", "days above 95", "station history")
    if any(
        phrase in lower
        for phrase in (
            "how often",
            "getting worse",
            "days per year",
            "days a year",
            "days above 95",
            "hot days",
            "ghcn",
            "station history",
            "frequency",
        )
    ) and not any(w in lower for w in ("cooling center", "where should", "proposal", "recommend")):
        return Intent(
            intent_type="heat_frequency",
            city=s.city,
            forecast_high_f=forecast_high_f,
        )

    # 7b. Check standalone equity_audit ("run the post-hoc equity audit", "equity audit comparing")
    if "equity audit" in lower and not any(
        w in lower for w in ("recommend 3", "where should", "cooling center sites")
    ):
        return Intent(
            intent_type="equity_audit",
            city=s.city,
        )

    # 8. Check demographics ("who lives", "demographics", "car-free", "seniors") for a specific spot
    if (
        any(
            phrase in lower
            for phrase in ("who lives", "demographics", "car-free", "no vehicle", "seniors", "poverty")
        )
        and (lat is not None or loc_query is not None)
        and not any(w in lower for w in ("cooling center", "where should", "rank", "offset", "why is"))
    ):
        return Intent(
            intent_type="demographics",
            city=s.city,
            location_query=loc_query or (f"{lat}, {lon}" if lat is not None else None),
            lat=lat,
            lon=lon,
        )

    # 9. Check explain_location ("what is the heat offset in", "why is ... hot", "nobody measured", specific lat/lon or neighborhood)
    if (lat is not None or loc_query is not None) and not any(
        w in lower for w in ("where should", "3 cooling", "three cooling", "rank", "council proposal")
    ):
        return Intent(
            intent_type="explain_location",
            city=s.city,
            location_query=loc_query or f"{lat}, {lon}",
            lat=lat,
            lon=lon,
            forecast_high_f=forecast_high_f,
        )

    # 10. Default to site_selection (ranking top K cooling centers + equity audit + council proposal)
    unmeasured_only = "unmeasured only" in lower or "only unmeasured" in lower
    return Intent(
        intent_type="site_selection",
        city=s.city,
        k_sites=s.scenario_sites,
        min_spacing_m=2000,
        radius_m=800.0,
        forecast_high_f=forecast_high_f,
        unmeasured_only=unmeasured_only,
    )


def _generate_llm_narrative(data_result: DataResult, user_message: str) -> str | None:
    """Stage 4: Optional Gemini 3 NarrativeWriterAgent pass (`tools=[]`, `GOOGLE_CLOUD_LOCATION=global`)."""
    s = Settings()
    if not s.use_llm_writer:
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            vertexai=True,
            project=s.project,
            location=s.google_cloud_location,
        )
        cite_ids = [p.provenance_id for p in data_result.provenance] or ["P1"]
        prompt = (
            f"You are the NarrativeWriterAgent for the {s.city}, GA Urban Heat Planning Assistant.\n"
            f"User question: {user_message}\n\n"
            "Write a concise, council-ready markdown response using ONLY the exact numbers in the "
            f"following structured DataResult JSON. Cite provenance tags {cite_ids} (e.g., [P1]) "
            "in every paragraph with numbers. Always frame heat predictions as °F offsets relative "
            "to the 82.1°F Atlanta campaign mean (never as a standalone absolute temperature forecast).\n\n"
            f"DataResult JSON:\n{data_result.model_dump_json()}"
        )
        resp = client.models.generate_content(
            model=s.writer_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=2048,
            ),
        )
        return resp.text if resp and resp.text else None
    except Exception as exc:
        log.warning("Gemini 3 writer pass skipped (%s); using deterministic template.", exc)
        return None


def run_plan_turn(
    message: str,
    session_state: dict[str, Any] | None = None,
    use_llm_classifier: bool = False,
    use_llm_writer: bool | None = None,
) -> AgentApiResponse:
    """Execute one full 5-stage turn of the `HeatPlannerOrchestrator` and return `AgentApiResponse`."""
    _ = use_llm_classifier
    t0 = time.monotonic()
    state = session_state if session_state is not None else {}
    ctx = _SessionContextAdapter(state)

    # Stage 1: Intent Classification
    intent = classify_intent(message, state)

    # Stage 2: Deterministic Scope & Clarification Gate
    if intent.intent_type == "ambiguous_prompt":
        data_res = DataResult(
            status="needs_clarification",
            intent_type=intent.intent_type,
            error_message=intent.clarification_question,
            provenance=[],
        )
        narrative, report = verify_narrative(
            intent.clarification_question or "Please clarify your planning request.",
            data_res,
        )
        return AgentApiResponse(
            status="needs_clarification",
            intent=intent,
            data_result=data_res,
            narrative_markdown=narrative,
            verification=report,
            latency_ms=int((time.monotonic() - t0) * 1000),
        )

    if intent.intent_type in ("out_of_scope_city", "causal_simulation", "future_forecast", "race_in_model"):
        out_status = "out_of_scope" if intent.intent_type == "out_of_scope_city" else "refused"
        data_res = DataResult(
            status=out_status,  # type: ignore[arg-type]
            intent_type=intent.intent_type,
            error_message=intent.refusal_reason,
            provenance=[],
        )
        narrative = f"**Scope & Methodological Refusal (`{intent.intent_type}`):** {intent.refusal_reason}"
        return AgentApiResponse(
            status=out_status,  # type: ignore[arg-type]
            intent=intent,
            data_result=data_res,
            narrative_markdown=narrative,
            verification=verify_narrative(narrative, data_res)[1],
            latency_ms=int((time.monotonic() - t0) * 1000),
        )

    # Resolve location if intent requires a coordinate
    lat = intent.lat
    lon = intent.lon
    prov_list: list[Provenance] = []
    if intent.intent_type in ("explain_location", "demographics") and (lat is None or lon is None):
        loc_res = resolve_location(intent.location_query or message)
        for p in loc_res.get("provenance") or []:
            prov_list.append(Provenance.model_validate(p) if isinstance(p, dict) else p)
        if loc_res["status"] != "success":
            out_st = "out_of_scope" if loc_res["status"] == "out_of_scope" else "refused"
            data_res = DataResult(
                status=out_st,  # type: ignore[arg-type]
                intent_type=intent.intent_type,
                error_message=loc_res.get("error_message"),
                provenance=prov_list,
            )
            narrative = (
                f"**Out of Campaign Footprint (`{intent.location_query or message}`):** "
                f"{loc_res.get('error_message')} [P1]"
                if prov_list
                else f"**Out of Campaign Footprint (`{intent.location_query or message}`):** {loc_res.get('error_message')}"
            )
            return AgentApiResponse(
                status=out_st,  # type: ignore[arg-type]
                intent=intent,
                data_result=data_res,
                narrative_markdown=narrative,
                verification=verify_narrative(narrative, data_res)[1],
                latency_ms=int((time.monotonic() - t0) * 1000),
            )
        lat = float(loc_res["data"]["lat"])
        lon = float(loc_res["data"]["lon"])
        intent.lat = lat
        intent.lon = lon

    # Stage 3: Deterministic MCP Toolbox Data Router
    data_res: DataResult
    if intent.intent_type == "explain_location":
        exp_res = explain_heat_offset(
            lat=float(lat or 33.7195),
            lon=float(lon or -84.4252),
            forecast_high_f=float(intent.forecast_high_f or 0.0),
            tool_context=ctx,  # type: ignore[arg-type]
        )
        for p in exp_res.get("provenance") or []:
            prov_list.append(Provenance.model_validate(p) if isinstance(p, dict) else p)
        for idx_p, p in enumerate(prov_list, start=1):
            p.provenance_id = f"P{idx_p}"

        if exp_res["status"] != "success":
            data_res = DataResult(
                status="out_of_scope" if exp_res["status"] == "out_of_scope" else "error",
                intent_type=intent.intent_type,
                error_message=exp_res.get("error_message"),
                provenance=prov_list,
            )
            narrative = f"**Out of Campaign Footprint:** {exp_res.get('error_message')}"
            return AgentApiResponse(
                status=data_res.status,  # type: ignore[arg-type]
                intent=intent,
                data_result=data_res,
                narrative_markdown=narrative,
                verification=verify_narrative(narrative, data_res)[1],
                latency_ms=int((time.monotonic() - t0) * 1000),
            )

        sa = SiteAssessment.model_validate(exp_res["data"]["site_assessment"])
        data_res = DataResult(
            status="success",
            intent_type=intent.intent_type,
            sites=[sa],
            provenance=prov_list,
        )

    elif intent.intent_type == "compare_sites":
        cmp_res = compare_sites(
            ranks=intent.compared_ranks or [1, 2, 3, 4],
            tool_context=ctx,  # type: ignore[arg-type]
        )
        for p in cmp_res.get("provenance") or []:
            prov_list.append(Provenance.model_validate(p) if isinstance(p, dict) else p)
        for idx_p, p in enumerate(prov_list, start=1):
            p.provenance_id = f"P{idx_p}"

        cmp_data = cmp_res.get("data") or {}
        compared_sites = [
            SiteAssessment.model_validate(s_item)
            for s_item in (cmp_data.get("compared_sites") or [])
        ]
        data_res = DataResult(
            status="success",
            intent_type=intent.intent_type,
            sites=compared_sites[:3],
            runner_up_sites=compared_sites[3:],
            comparison_table=cmp_data.get("displacement_deltas"),
            provenance=prov_list,
        )

    elif intent.intent_type == "heat_frequency":
        hf_res = get_heat_frequency(threshold_f=95.0, offset_f=0.0, tool_context=ctx)  # type: ignore[arg-type]
        for p in hf_res.get("provenance") or []:
            prov_list.append(Provenance.model_validate(p) if isinstance(p, dict) else p)
        for idx_p, p in enumerate(prov_list, start=1):
            p.provenance_id = f"P{idx_p}"
        hf_d = hf_res["data"]
        hf_summary = CityHeatFrequencySummary(
            years_covered=str(hf_d["years_covered"]),
            full_years_count=int(hf_d["full_years_count"]),
            avg_days_ge_90f=float(hf_d["avg_days_ge_90f"]),
            avg_days_ge_95f=float(hf_d["avg_days_ge_95f"]),
            avg_days_ge_100f=float(hf_d["avg_days_ge_100f"]),
            hottest_temp_recorded_f=float(hf_d["hottest_temp_recorded_f"]),
            trend_days_per_decade=hf_d.get("trend_days_per_decade"),
            by_year=list(hf_d.get("by_year") or []),
        )
        data_res = DataResult(
            status="success",
            intent_type=intent.intent_type,
            heat_frequency=hf_summary,
            provenance=prov_list,
        )

    elif intent.intent_type == "demographics":
        exp_res = explain_heat_offset(
            lat=float(lat or 33.7195),
            lon=float(lon or -84.4252),
            tool_context=ctx,  # type: ignore[arg-type]
        )
        for p in exp_res.get("provenance") or []:
            prov_list.append(Provenance.model_validate(p) if isinstance(p, dict) else p)
        for idx_p, p in enumerate(prov_list, start=1):
            p.provenance_id = f"P{idx_p}"
        sa = SiteAssessment.model_validate(exp_res["data"]["site_assessment"])
        data_res = DataResult(
            status="success",
            intent_type=intent.intent_type,
            sites=[sa],
            provenance=prov_list,
        )

    elif intent.intent_type == "equity_audit":
        audit_res = run_equity_audit(
            site_geo_ids=["13121007603", "13121004200", "13121004800"],
            tool_context=ctx,  # type: ignore[arg-type]
        )
        for p in audit_res.get("provenance") or []:
            prov_list.append(Provenance.model_validate(p) if isinstance(p, dict) else p)
        for idx_p, p in enumerate(prov_list, start=1):
            p.provenance_id = f"P{idx_p}"
        audit_obj = EquityAudit.model_validate(audit_res["data"])
        data_res = DataResult(
            status="success",
            intent_type=intent.intent_type,
            equity_audit=audit_obj,
            provenance=prov_list,
        )

    else:
        # site_selection -> full PlacementRecommendation
        rec_res = assemble_placement_recommendation(
            k=intent.k_sites,
            forecast_high_f=float(intent.forecast_high_f or 0.0),
            unmeasured_only=bool(intent.unmeasured_only),
            tool_context=ctx,  # type: ignore[arg-type]
        )
        for p in rec_res.get("provenance") or []:
            prov_list.append(Provenance.model_validate(p) if isinstance(p, dict) else p)
        for idx_p, p in enumerate(prov_list, start=1):
            p.provenance_id = f"P{idx_p}"

        rec_obj = PlacementRecommendation.model_validate(rec_res["data"])
        data_res = DataResult(
            status="success",
            intent_type=intent.intent_type,
            sites=rec_obj.sites,
            runner_up_sites=rec_obj.runner_up_sites,
            heat_frequency=rec_obj.heat_frequency,
            equity_audit=rec_obj.equity_audit,
            recommendation=rec_obj,
            provenance=prov_list,
        )

    # Stage 4: NarrativeWriterAgent (or deterministic renderer)
    draft_narrative = (
        None if use_llm_writer is False else _generate_llm_narrative(data_res, message)
    )
    if not draft_narrative:
        draft_narrative = render_deterministic_fallback(data_res)

    # Stage 5: GroundingVerifier
    verified_narrative, report = verify_narrative(draft_narrative, data_res)

    return AgentApiResponse(
        status="success",
        intent=intent,
        data_result=data_res,
        narrative_markdown=verified_narrative,
        verification=report,
        latency_ms=int((time.monotonic() - t0) * 1000),
    )
