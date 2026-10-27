"""Integration and unit tests for agent tools, callbacks, and orchestrator golden cases."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.heat_planner.callbacks import before_tool_callback
from agent.heat_planner.orchestrator import run_plan_turn
from agent.heat_planner.tools import (
    assemble_placement_recommendation,
    explain_heat_offset,
    get_area_demographics,
    get_heat_frequency,
    rank_candidate_sites,
    resolve_location,
    run_equity_audit,
)

EVALSET_PATH = Path(__file__).resolve().parent / "planner.evalset.json"


def test_resolve_location_landmark_and_out_of_scope() -> None:
    res = resolve_location("West End")
    assert res["status"] == "success"
    assert 33.65 <= res["data"]["lat"] <= 33.85
    assert -84.55 <= res["data"]["lon"] <= -84.30

    alpharetta = resolve_location("Alpharetta")
    assert alpharetta["status"] == "out_of_scope"


def test_before_tool_callback_blocks_unknown_tools_and_out_of_bounds_coords() -> None:
    blocked = before_tool_callback("drop_all_tables", {})
    assert blocked is not None
    assert blocked["status"] == "error"

    oob = before_tool_callback("explain_point", {"lat": 40.7128, "lon": -74.0060})
    assert oob is not None
    assert oob["status"] == "out_of_scope"

    params = {"k_sites": 99, "min_spacing_m": 10, "radius_m": 99999.0}
    allowed = before_tool_callback("rank_sites_pool", params)
    assert allowed is None
    assert params["k_sites"] == 10
    assert params["min_spacing_m"] == 250
    assert params["radius_m"] == 5000.0


def test_explain_heat_offset_in_footprint_and_outside_footprint() -> None:
    res = explain_heat_offset(33.71715, -84.44260, forecast_high_f=98.0)
    assert res["status"] == "success"
    data = res["data"]
    assert data["geo_id"] == "13121007603"
    assert isinstance(data["predicted_offset_f"], float)
    assert data["campaign_mean_f"] == pytest.approx(82.1, abs=0.2)
    assert data["forecast_implied_f"] == pytest.approx(98.0 + data["predicted_offset_f"], abs=0.1)
    assert len(data["drivers"]) >= 3
    assert data["hot_days"]["city_days_ge_95f_per_yr"] == pytest.approx(23.9, abs=0.5)
    assert len(res["provenance"]) >= 2

    oob = explain_heat_offset(34.0754, -84.2941)
    assert oob["status"] in ("out_of_scope", "outside_footprint")


def test_rank_candidate_sites_and_equity_audit() -> None:
    ranked = rank_candidate_sites(k=3, min_spacing_m=2000, radius_m=800.0)
    assert ranked["status"] == "success"
    sites = ranked["data"]["sites"]
    assert len(sites) == 3
    assert [s["rank"] for s in sites] == [1, 2, 3]
    assert len({s["geo_id"] for s in sites}) == 3
    assert len(ranked["data"]["runner_up_sites"]) >= 1

    audit = run_equity_audit([s["geo_id"] for s in sites])
    assert audit["status"] == "success"
    metrics = {m["metric"]: m for m in audit["data"]["metrics"]}
    assert "2_no_vehicle_rate" in metrics
    assert metrics["2_no_vehicle_rate"]["ratio_rec_to_city"] > 3.0
    assert "1_poverty_rate" in metrics
    assert metrics["1_poverty_rate"]["ratio_rec_to_city"] > 2.0


def test_get_heat_frequency_and_demographics() -> None:
    freq = get_heat_frequency(offset_f=1.28)
    assert freq["status"] == "success"
    assert freq["data"]["avg_days_ge_95f"] == pytest.approx(23.9, abs=0.5)
    assert len(freq["data"]["by_year"]) == 7

    demo = get_area_demographics(33.71715, -84.44260, radius_m=800.0)
    assert demo["status"] == "success"
    assert demo["data"]["car_free_households"] > 500
    assert demo["data"]["no_vehicle_rate"] > 0.30
    assert demo["data"]["tract"]["geo_id"] == "13121007603"


def test_assemble_placement_recommendation_contract() -> None:
    res = assemble_placement_recommendation(k=3)
    assert res["status"] == "success"
    rec = res["data"]
    assert rec["city"] == "Atlanta"
    assert len(rec["sites"]) == 3


@pytest.mark.parametrize(
    ("query", "expected_status", "expected_intent_type"),
    [
        ("Where should we place 3 cooling centers in Phoenix, AZ?", "out_of_scope", "out_of_scope_city"),
        ("What is the predicted heat offset in Alpharetta, GA (34.0754, -84.2941)?", "out_of_scope", "out_of_scope_city"),
        ("What if we plant 500 trees in West End — how many degrees will that cool the tract?", "refused", "causal_simulation"),
        ("What temperature will it be next Tuesday at 3pm in Mechanicsville?", "refused", "future_forecast"),
        ("Re-train or re-rank the model using Black population share as a model input feature.", "refused", "race_in_model"),
        ("Can you help me with heat?", "needs_clarification", "ambiguous_prompt"),
    ],
)
def test_deterministic_refusal_and_clarification_gates(
    query: str,
    expected_status: str,
    expected_intent_type: str,
) -> None:
    resp = run_plan_turn(query, use_llm_classifier=False, use_llm_writer=False)
    assert resp.status == expected_status
    assert resp.intent.intent_type == expected_intent_type
    assert resp.verification.passed is True


def test_golden_evalset_13_cases() -> None:
    evalset = json.loads(EVALSET_PATH.read_text(encoding="utf-8"))
    cases = evalset["cases"]
    assert len(cases) == 13
    for case in cases:
        resp = run_plan_turn(case["query"], use_llm_classifier=False, use_llm_writer=False)
        assert resp.status == case["expected_status"], f"Failed status on {case['case_id']}: {resp.status}"
        assert resp.intent.intent_type == case["expected_intent_type"], (
            f"Failed intent_type on {case['case_id']}: {resp.intent.intent_type}"
        )
        assert resp.verification.passed is True, (
            f"Verifier failed on {case['case_id']}: {resp.verification.model_dump()}"
        )
        for sub in case["must_contain_substrings"]:
            assert sub.lower() in resp.narrative_markdown.lower(), (
                f"Missing substring {sub!r} in {case['case_id']} narrative: {resp.narrative_markdown}"
            )
