"""Typed Pydantic v2 contracts for the Atlanta Urban Heat Planning Assistant.

Covers all Stage 2 (`heat-planner-api`) schemas specified in
`docs/agents/IMPLEMENTATION_PLAN.md` Section 3:
  - `Intent` (`docs/contracts/intent.schema.json`)
  - `DataRequest` (`docs/contracts/data_request.schema.json`)
  - `Provenance` (`docs/contracts/provenance.schema.json`)
  - `DataResult` (`docs/contracts/data_result.schema.json`)
  - `PlacementRecommendation` (`docs/contracts/placement_recommendation.schema.json`)
  - `AgentApiResponse` (`docs/contracts/agent_api_response.schema.json`)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


Status = Literal[
    "success", "out_of_scope", "not_found", "no_data", "needs_clarification", "refused", "error"
]
IntentType = Literal[
    "site_selection",
    "explain_location",
    "compare_sites",
    "heat_frequency",
    "demographics",
    "equity_audit",
    "out_of_scope_city",
    "causal_simulation",
    "future_forecast",
    "race_in_model",
    "ambiguous_prompt",
]


class Intent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="1.0.0")
    intent_type: IntentType
    city: str = Field(default="Atlanta")
    location_query: str | None = Field(default=None)
    lat: float | None = Field(default=None)
    lon: float | None = Field(default=None)
    k_sites: int = Field(default=3, ge=1, le=10)
    min_spacing_m: int = Field(default=2000, ge=0, le=10000)
    radius_m: float = Field(default=800.0, ge=100.0, le=5000.0)
    forecast_high_f: float | None = Field(default=None)
    unmeasured_only: bool = Field(default=False)
    compared_ranks: list[int] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    clarification_question: str | None = Field(default=None)
    refusal_reason: str | None = Field(default=None)


class DataRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="1.0.0")
    intent_type: IntentType
    mcp_tool_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class Provenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="1.0.0")
    provenance_id: str = Field(description="Citation tag e.g. 'P1', 'P2'.")
    source_type: Literal["mcp_toolbox", "bq_direct"] = Field(default="mcp_toolbox")
    tool_name: str = Field(description="Python domain wrapper or orchestrator step.")
    mcp_tool_name: str = Field(description="Tool invoked on heat-toolbox.")
    sql_object: str = Field(description="Underlying BigQuery view/table/model in a4i_semantic or a4i_ml.")
    parameters: dict[str, Any] = Field(default_factory=dict)
    row_count: int = Field(ge=0)
    model_version: str | None = Field(default="offset_model_v1")
    queried_at_utc: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class Driver(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature: str = Field(description="Feature column name from point_features().")
    attribution: float = Field(
        description="Signed °F contribution from ML.EXPLAIN_PREDICT vs. baseline."
    )


class CatchmentDemographics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geo_id: str
    radius_m: float = Field(default=800.0)
    tract_count: int = Field(default=1)
    tract_geo_ids: list[str] = Field(default_factory=list)
    total_pop: int = Field(default=0)
    pop_65_plus: int = Field(default=0)
    share_65_plus: float = Field(default=0.0)
    households: int = Field(default=0)
    car_free_households: int = Field(default=0)
    no_vehicle_rate: float = Field(default=0.0)
    poverty_rate: float = Field(default=0.0)
    median_income: float | None = Field(default=None)


class SiteHotDays(BaseModel):
    model_config = ConfigDict(extra="forbid")

    city_days_ge_90f_per_yr: float = Field(default=78.0)
    city_days_ge_95f_per_yr: float = Field(default=23.9)
    city_days_ge_100f_per_yr: float = Field(default=1.6)
    expected_days_ge_90f_equiv: float = Field(default=88.0)
    expected_days_ge_95f_equiv: float = Field(default=35.0)
    expected_days_ge_100f_equiv: float = Field(default=4.0)
    extra_days_ge_95f_equiv: float = Field(default=11.1)


class SiteAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    point_id: str
    lat: float
    lon: float
    geo_id: str
    neighborhood: str
    predicted_offset_f: float
    campaign_mean_f: float = Field(default=82.1)
    forecast_high_f: float | None = Field(default=None)
    forecast_implied_f: float | None = Field(default=None)
    priority_score: float
    unmeasured: bool
    spacing_conflict_with_rank: int | None = Field(default=None)
    drivers: list[Driver]
    demographics: CatchmentDemographics
    hot_days: SiteHotDays
    google_maps_url: str | None = Field(default=None)
    google_maps_walking_url: str | None = Field(default=None)
    why_here: str


class CityHeatFrequencySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    years_covered: str = Field(default="2019-2025")
    full_years_count: int = Field(default=7)
    avg_days_ge_90f: float = Field(default=78.0)
    avg_days_ge_95f: float = Field(default=23.9)
    avg_days_ge_100f: float = Field(default=1.6)
    hottest_temp_recorded_f: float = Field(default=104.0)
    trend_days_per_decade: float | None = Field(default=None)
    by_year: list[dict[str, Any]] = Field(default_factory=list)


class EquityAuditMetricRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    recommended_sites: float
    city_overall: float
    ratio_rec_to_city: float | None = Field(default=None)


class EquityAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_geo_ids: list[str]
    metrics: list[EquityAuditMetricRow]
    ratios: dict[str, float]
    deltas: dict[str, float]
    passes_equity_check: bool
    summary: str


class PlacementRecommendation(BaseModel):
    """The required challenge output artifact (`docs/contracts/placement_recommendation.schema.json`)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="1.0.0")
    city: str = Field(default="Atlanta")
    track: Literal["today", "budget", "decade"] = Field(default="budget")
    intervention: str = Field(
        default="3 permanent walkable cooling centers (This budget cycle)"
    )
    model_version: str = Field(default="offset_model_v1")
    campaign_mean_f: float = Field(default=82.1)
    sites: list[SiteAssessment]
    runner_up_sites: list[SiteAssessment] = Field(default_factory=list)
    heat_frequency: CityHeatFrequencySummary
    equity_audit: EquityAudit
    proposal_markdown: str
    limitations: list[str]


class DataResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="1.0.0")
    status: Status
    intent_type: IntentType
    sites: list[SiteAssessment] = Field(default_factory=list)
    runner_up_sites: list[SiteAssessment] = Field(default_factory=list)
    comparison_table: list[dict[str, Any]] | None = Field(default=None)
    heat_frequency: CityHeatFrequencySummary | None = Field(default=None)
    equity_audit: EquityAudit | None = Field(default=None)
    recommendation: PlacementRecommendation | None = Field(default=None)
    provenance: list[Provenance] = Field(default_factory=list)
    error_message: str | None = Field(default=None)


class VerificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    ungrounded_numbers: list[str] = Field(default_factory=list)
    framing_violations: list[str] = Field(default_factory=list)
    missing_citations: list[str] = Field(default_factory=list)
    fallback_used: bool = Field(default=False)


class AgentApiResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="1.0.0")
    status: Status
    intent: Intent
    data_result: DataResult
    narrative_markdown: str
    verification: VerificationReport
    latency_ms: int = Field(ge=0)


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Status
    data: dict[str, Any] | list[Any] | None = Field(default=None)
    error_message: str | None = Field(default=None)
    provenance: list[Provenance] = Field(default_factory=list)
    model_version: str | None = Field(default=None)
    caveats: list[str] = Field(default_factory=list)


class HeatExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: float
    lon: float
    geo_id: str
    in_footprint: bool
    predicted_offset_f: float
    baseline_offset_f: float
    campaign_mean_f: float
    forecast_high_f: float | None = Field(default=None)
    forecast_implied_f: float | None = Field(default=None)
    drivers: list[Driver]
    measured_nearby: bool
    expected_days_ge_95f_equiv_per_yr: float | None = Field(default=None)
    city_days_ge_95f_per_yr: float | None = Field(default=None)
    extra_days_ge_95f_equiv_per_yr: float | None = Field(default=None)
    model_version: str
