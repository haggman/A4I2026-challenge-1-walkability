"""What heat-ui reads from heat-planner-api: POST /api/v1/plan and GET /api/v1/tracts.

heat-planner-api owns its contracts (docs/contracts/*.schema.json). Over HTTP it serves them
reshaped for this UI by _to_api_dict in agent/heat_planner/api.py; these models describe that
served shape, not the raw schemas. The intent mapping happens there: k_sites -> k,
refusal intents ("out_of_scope_city", "causal_simulation", ...) -> "out_of_scope",
status "success" -> "ok". ui_service/samples/ holds real responses in this shape.

Models ignore unknown fields (tolerant reader) so additions upstream don't break the UI.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0.0"

ResponseStatus = Literal["ok", "no_data", "out_of_scope", "needs_clarification", "error"]
IntentType = Literal[
    "site_selection", "explain_location", "compare_sites", "heat_frequency", "demographics",
    "draft_proposal", "equity_audit", "generic_data", "out_of_scope",
]
RefusalReason = Literal["other_city", "outside_footprint", "intervention_simulation",
                        "race_targeting", "weather_forecast", "other"]


class Upstream(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class LocationRef(Upstream):
    label: str | None = None
    lat: float | None = None
    lon: float | None = None
    geo_id: str | None = None


class Intent(Upstream):
    schema_version: str = SCHEMA_VERSION
    intent_type: IntentType
    status: ResponseStatus
    locations: list[LocationRef] = []
    candidate_ranks: list[int] = []
    k: int = 3
    radius_m: float = 800.0
    min_spacing_m: float = 2000.0
    threshold_f: float = 95.0
    forecast_high_f: float | None = None
    unmeasured_only: bool = False
    missing_parameters: list[str] = []
    clarifying_question: str | None = None
    refusal_reason: RefusalReason | None = None
    refusal_explanation: str | None = None


class Provenance(Upstream):
    provenance_id: str                      # "P1", "P2", ...
    tool_name: str
    mcp_tool_name: str | None = None
    source_type: Literal["mcp_toolbox", "session_state"]
    sql_object: str
    parameters: dict[str, Any] = {}
    model_version: str | None = "offset_model_v1"
    timestamp_utc: str
    row_count: int
    latency_ms: int


class DataResult(Upstream):
    status: ResponseStatus
    intent_type: str
    rows: list[dict[str, Any]] = []
    summary_metrics: dict[str, float | int | str] = {}
    provenance: list[Provenance] = []
    error_message: str | None = None


class Driver(Upstream):
    """One ML.EXPLAIN_PREDICT attribution, already in planner English."""
    feature: str                            # model column, e.g. "pop_density_km2"
    label: str                              # planner English, e.g. "Street density"
    attribution_f: float                    # signed °F contribution


class CatchmentDemographics(Upstream):
    """Mirrors a4i_semantic.vulnerable_population(lat, lon, radius_m)."""
    radius_m: float
    tracts_within_radius: int
    population_within_radius: int
    pop_65_plus_within_radius: int
    car_free_households_within_radius: int
    households_within_radius: int
    share_65_plus_within_radius: float      # 0..1
    no_vehicle_rate_within_radius: float    # 0..1
    pop_weighted_poverty_rate: float        # 0..1
    tract_geo_ids: list[str] = []


class SiteHotDays(Upstream):
    """Mirrors a4i_semantic.site_hot_days(offset_f)."""
    offset_f: float
    mean_days_ge_95f_equiv_per_yr: float
    city_baseline_days_ge_95f_per_yr: float
    extra_days_ge_95f_equiv_per_yr: float
    mean_days_ge_90f_equiv_per_yr: float | None = None
    mean_days_ge_100f_equiv_per_yr: float | None = None
    full_years_counted: int | None = None


class SiteAssessment(Upstream):
    rank: int
    site_id: str
    lat: float
    lon: float
    address_hint: str | None = None         # neighborhood name for display
    geo_id: str
    predicted_offset_f: float
    implied_local_high_f: float | None = None
    unmeasured: bool
    drivers: list[Driver] = []
    catchment: CatchmentDemographics | None = None
    hot_days: SiteHotDays | None = None
    priority_score: float
    why: str | None = None
    provenance_ids: list[str] = []
    # Site tract's demographics for "Who lives here vs. Atlanta" (0..1 rates)
    tract_no_vehicle_rate: float | None = None
    tract_share_65_plus: float | None = None
    tract_poverty_rate: float | None = None
    # Runner-ups only: why it wasn't picked, e.g. "Within 2.0 km of Site 1"
    passed_over_reason: str | None = None


class HeatDaysYear(Upstream):
    year: int
    days_ge_90_f: int
    days_ge_95_f: int
    days_ge_100_f: int


class CityHeatFrequencySummary(Upstream):
    years: list[HeatDaysYear] = []
    mean_days_ge_95_f: float | None = None
    ols_slope_days_ge_95_per_yr: float | None = None
    caveat: str | None = None


AuditMeasure = Literal["median_income", "poverty_rate", "no_vehicle_rate", "share_65_plus"]


class AuditMeasureRow(Upstream):
    measure: AuditMeasure
    sites_value: float                      # population-weighted over the recommended tracts
    city_value: float                       # a4i_semantic.audit_city_baseline
    ratio: float                            # sites / city


class RacialCompositionRow(Upstream):
    """Post-hoc output check only (sql/audit/audit.sql). Never a model or ranking input."""
    group: str
    sites_share: float
    city_share: float


class EquityAudit(Upstream):
    site_geo_ids: list[str]
    residents_in_site_tracts: int | None = None
    measures: list[AuditMeasureRow]
    verdict: str | None = None
    racial_composition: list[RacialCompositionRow] = []   # shown only on request
    provenance_ids: list[str] = []


class PlacementRecommendation(Upstream):
    city: str = "Atlanta"
    track: str = "budget"
    scenario: str
    forecast_high_f: float | None = None
    campaign_mean_f: float = 82.062
    sites: list[SiteAssessment]
    runner_up_sites: list[SiteAssessment] = []
    heat_frequency: CityHeatFrequencySummary | None = None
    equity_audit: EquityAudit | None = None
    proposal_markdown: str | None = None
    # The two prose sections the memo template can't build from data
    proposal_sections: dict[Literal["why_these", "what_this_displaces"], str] = {}
    limitations: list[str] = []
    model_version: str = "offset_model_v1"
    generated_at: str


class VerificationReport(Upstream):
    passed: bool
    ungrounded_numbers: list[str] = []
    framing_violations: list[str] = []
    retries: int = 0
    fallback_used: bool = False


class AgentApiResponse(Upstream):
    schema_version: str = SCHEMA_VERSION
    trace_id: str
    status: ResponseStatus
    intent: Intent
    data_result: DataResult | None = None
    recommendation: PlacementRecommendation | None = None
    narrative: str                          # markdown with [P1] citations
    citations: list[Provenance] = []
    verification: VerificationReport
    total_latency_ms: int
    error_message: str | None = None


class TractProperties(Upstream):
    geo_id: str
    predicted_offset_f: float | None = None   # tract mean of a4i_ml.grid_predictions
    no_vehicle_rate: float | None = None      # 0..1, a4i_semantic.dim_tract
    share_65_plus: float | None = None
    poverty_rate: float | None = None
    population: int | None = None


class TractFeature(Upstream):
    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any]                  # TIGER/Line polygon (public domain)
    properties: TractProperties


class TractLayer(Upstream):
    """GET /api/v1/tracts on heat-planner-api (heat-toolbox tool `tract_layer`).

    The choropleth and the audit scatter need every tract; AgentApiResponse only carries the
    chosen sites. Cached by both services; it changes only when the model is re-scored.
    """
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[TractFeature]
    model_version: str = "offset_model_v1"


class PlanRequest(Upstream):
    """Draft of POST /api/v1/plan's body."""
    session_id: str
    message: str = Field(max_length=2000)
