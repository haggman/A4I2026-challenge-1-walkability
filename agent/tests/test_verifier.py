"""Unit tests for the deterministic GroundingVerifier and template fallback."""

from __future__ import annotations

from agent.heat_planner.schemas import (
    CatchmentDemographics,
    DataResult,
    Driver,
    Provenance,
    SiteAssessment,
    SiteHotDays,
)
from agent.heat_planner.verifier import render_deterministic_fallback, verify_narrative


def _sample_data_result() -> DataResult:
    site = SiteAssessment(
        rank=1,
        point_id="g_33.7172_-84.4426",
        lat=33.71715,
        lon=-84.44260,
        geo_id="13121007603",
        neighborhood="Venetian Hills / Oakland City",
        predicted_offset_f=1.28,
        campaign_mean_f=82.1,
        forecast_high_f=98.0,
        forecast_implied_f=99.28,
        priority_score=1.791,
        unmeasured=True,
        drivers=[
            Driver(feature="housing_within_1500m", attribution=1.12),
            Driver(feature="water_share", attribution=0.111),
            Driver(feature="pop_density_km2", attribution=0.079),
        ],
        demographics=CatchmentDemographics(
            geo_id="13121007603",
            radius_m=800.0,
            tract_count=1,
            tract_geo_ids=["13121007603"],
            total_pop=3943,
            pop_65_plus=742,
            share_65_plus=0.1882,
            households=2001,
            car_free_households=1128,
            no_vehicle_rate=0.5637,
            poverty_rate=0.4856,
            median_income=14630.0,
        ),
        hot_days=SiteHotDays(
            city_days_ge_90f_per_yr=78.0,
            city_days_ge_95f_per_yr=23.9,
            city_days_ge_100f_per_yr=1.6,
            expected_days_ge_90f_equiv=88.9,
            expected_days_ge_95f_equiv=33.0,
            expected_days_ge_100f_equiv=3.6,
            extra_days_ge_95f_equiv=9.1,
        ),
        google_maps_url="https://www.google.com/maps/search/?api=1&query=33.71715,-84.44260",
        google_maps_walking_url="https://www.google.com/maps/dir/?api=1&destination=33.71715,-84.44260&travelmode=walking",
        why_here="Predicted +1.28°F above the Atlanta campaign average (82.1°F).",
    )
    prov = Provenance(
        provenance_id="P1",
        tool_name="explain_heat_offset",
        mcp_tool_name="explain_point",
        sql_object="a4i_ml.offset_model_v1",
        parameters={"lat": 33.71715, "lon": -84.44260},
        row_count=1,
    )
    return DataResult(
        status="success",
        intent_type="explain_location",
        sites=[site],
        provenance=[prov],
    )


def test_verifier_passes_grounded_offset_narrative() -> None:
    dr = _sample_data_result()
    narrative = (
        "Venetian Hills / Oakland City (`33.7172, -84.4426`, Tract `13121007603`) is predicted to run "
        "**+1.28 °F** above the Atlanta campaign mean (`82.1 °F`) [P1]. With a `98.0 °F` city forecast, "
        "that implies an effective afternoon peak near `~99.3 °F` (`33.0 days/yr` >=95°F-equivalent vs. "
        "`23.9 days/yr` citywide). The 800 m walkable catchment has `56.4%` car-free households (`1,128` HH) "
        "and `48.6%` poverty (`742` seniors 65+) [P1]."
    )
    final_md, report = verify_narrative(narrative, dr)
    assert report.passed is True
    assert report.fallback_used is False
    assert final_md == narrative
    assert report.ungrounded_numbers == []
    assert report.framing_violations == []
    assert report.missing_citations == []


def test_verifier_detects_ungrounded_numbers() -> None:
    dr = _sample_data_result()
    narrative = (
        "Venetian Hills is predicted to run +4.75 °F above the city mean with $99,999 median income [P1]."
    )
    final_md, report = verify_narrative(narrative, dr)
    assert report.passed is False
    assert report.fallback_used is True
    assert any("4.75" in n for n in report.ungrounded_numbers)
    assert "+1.28" in final_md


def test_verifier_detects_absolute_temperature_forecast_framing() -> None:
    dr = _sample_data_result()
    narrative = (
        "Tomorrow at 3pm it will be 99.3°F at Venetian Hills (`33.7172, -84.4426`) [P1]."
    )
    _final_md, report = verify_narrative(narrative, dr)
    assert report.passed is False
    assert report.fallback_used is True
    assert len(report.framing_violations) >= 1


def test_verifier_detects_missing_provenance_citations() -> None:
    dr = _sample_data_result()
    narrative = (
        "Venetian Hills runs +1.28 °F above the Atlanta campaign mean (82.1 °F) with 33.0 hot days/yr."
    )
    _final_md, report = verify_narrative(narrative, dr)
    assert report.passed is False
    assert report.fallback_used is True
    assert len(report.missing_citations) == 1


def test_deterministic_fallback_always_passes_verifier() -> None:
    dr = _sample_data_result()
    fallback_md = render_deterministic_fallback(dr)
    _final_md, report = verify_narrative(fallback_md, dr)
    assert report.passed is True
    assert report.fallback_used is False
