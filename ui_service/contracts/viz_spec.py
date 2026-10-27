"""VizSpec and FinalResponse: owned by the UI service (IMPLEMENTATION_PLAN.md sections 3 and 7).

VizSpecBuilder turns an AgentApiResponse into a VizSpec deterministically; the browser only
draws what VizSpec says. The plan's fields come first in each model; fields the P4 screens add
are grouped under "P4 screens" and are all optional, so a plain plan-shaped VizSpec still
validates.

Exported to docs/contracts/viz_spec.schema.json and final_response.schema.json.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .agent_api import (AgentApiResponse, AuditMeasure, Provenance, RacialCompositionRow,
                        SCHEMA_VERSION)

PrimaryView = Literal["map_and_table", "comparison_view", "driver_breakdown", "hot_days_chart",
                      "equity_audit_table", "proposal_document", "empty"]
FeatureType = Literal["recommended_site", "runner_up_site", "catchment", "tract", "grid_cell"]


class Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# ------------------------------------------------------------------ map

class MapFeatureProperties(Strict):
    feature_type: FeatureType
    rank: int | None = None                  # sites and their catchments
    geo_id: str | None = None
    label: str | None = None
    predicted_offset_f: float | None = None
    unmeasured: bool | None = None
    radius_m: float | None = None            # catchments
    no_vehicle_rate: float | None = None     # tracts (0..1), for the layer toggle
    share_65_plus: float | None = None


class MapFeature(Strict):
    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any]                 # GeoJSON Point or Polygon
    properties: MapFeatureProperties


class GeoJSONFeatureCollection(Strict):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[MapFeature]


# ------------------------------------------------------------------ sites

class RankedSiteRow(Strict):
    rank: int
    neighborhood: str | None
    geo_id: str
    predicted_offset_f: float
    unmeasured: bool
    no_vehicle_rate: float | None            # 0..1
    share_65_plus: float | None
    poverty_rate: float | None
    priority_score: float
    # P4 screens
    lat: float | None = None
    lon: float | None = None
    residents_reached: int | None = None     # catchment population ("[N] reached")
    hot_days_ge_95: float | None = None
    funded: bool = True                      # False for runner-ups
    passed_over_reason: str | None = None


class DriverBar(Strict):
    label: str
    attribution_f: float
    effect: Literal["adds_heat", "reduces_heat"]


class SiteDriverBars(Strict):
    rank: int
    bars: list[DriverBar]
    # P4 screens: the waterfall stacks bars from the city average up to the site's offset
    site_offset_f: float | None = None
    dominant_driver: str | None = None


class CompareBar(Strict):
    label: str
    site_value: float                        # 0..1
    city_value: float


class SiteDetail(Strict):
    """P4 Sites screen: the cards beside the waterfall for one site."""
    rank: int
    title: str                               # "Site 1 · Venetian Hills"
    lat: float
    lon: float
    geo_id: str
    hot_days_ge_95: float | None
    city_hot_days_ge_95: float | None
    residents_nearby: int | None
    radius_m: float | None
    cost_label: str = "[COST]"               # never invented: placeholder until finance confirms
    who_lives_here: list[CompareBar] = []    # no car, 65+ (site tract vs. Atlanta)
    diagnosis: str | None = None             # one line on the dominant driver; no fix simulated
    maps_url: str | None = None
    walking_url: str | None = None


class SiteComparison(Strict):
    """P4 "Why not site 4?": the last funded site vs. the first runner-up."""
    funded_rank: int
    runner_up_rank: int
    rows: list[dict[str, Any]]               # {"label", "funded", "runner_up", "delta"}
    reason: str | None


# ------------------------------------------------------------------ audit

class AuditComparisonRow(Strict):
    measure: AuditMeasure
    label: str
    sites_value: float
    city_value: float
    ratio: float
    # P4 screens
    higher_means_need: bool = True           # False for income
    toward_need: bool | None = None
    display_sites: str | None = None         # "44.1%", "$17,853"
    display_city: str | None = None


class AuditSummary(Strict):
    measures_toward_need: int
    measures_total: int
    verdict: str                             # one line for the banner
    detail: str | None = None                # the audit's full summary, when longer than a line


class ScatterPoint(Strict):
    geo_id: str
    predicted_offset_f: float
    vulnerability: float                     # 0..1, mean of no-car and 65+ percentiles
    site_rank: int | None = None
    funded: bool | None = None               # None for ordinary tracts


class AuditScatter(Strict):
    points: list[ScatterPoint]
    offset_split_f: float                    # quadrant lines: city medians
    vulnerability_split: float
    note: str | None = None


# ------------------------------------------------------------------ proposal

class ChecklistItem(Strict):
    label: str
    done: bool
    note: str | None = None                  # "done" / "needs a person"


class ProposalSiteRow(Strict):
    rank: int
    name: str
    location: str                            # "33.7195, -84.4252"
    offset: str                              # "+1.28°F"
    hot_days_ge_95: str
    nearby: str                              # "N (no car x% · 65+ y%)"
    cost: str = "[COST]"


class ProposalDoc(Strict):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True,
                              serialize_by_alias=True)
    title: str
    to: str = "Atlanta City Council"
    from_: str = Field("[Department / office]", alias="from")
    date: str = "[Date]"
    recommendation: str                      # built from data, not the LLM
    sites: list[ProposalSiteRow]
    why_these: str | None                    # LLM prose (verified upstream)
    what_this_displaces: str | None
    equity_check: str | None
    limitations: list[str]
    source_badges: list[str] = []            # "BQML", "Station history", "ACS", "EXPLAIN_PREDICT"
    checklist: list[ChecklistItem] = []
    status_line: str | None = None           # "Draft ready · every claim sourced · review before sending"


# ------------------------------------------------------------------ envelope

class VizSpec(Strict):
    schema_version: str = SCHEMA_VERSION
    primary_view: PrimaryView
    map_geojson: GeoJSONFeatureCollection | None = None
    ranked_table: list[RankedSiteRow] = []
    driver_bars: list[SiteDriverBars] = []
    vega_lite_spec: dict[str, Any] | None = None
    audit_table: list[AuditComparisonRow] = []
    # P4 screens
    site_details: list[SiteDetail] = []
    comparison: SiteComparison | None = None
    audit_summary: AuditSummary | None = None
    audit_scatter: AuditScatter | None = None
    racial_composition: list[RacialCompositionRow] = []   # rendered only behind "Show…"
    proposal: ProposalDoc | None = None
    limitations: list[str] = []
    mock: bool = False                       # True when built from samples/; UI shows a banner


class FinalResponse(AgentApiResponse):
    """AgentApiResponse plus the VizSpec heat-ui built from it."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    viz_spec: VizSpec | None = None


__all__ = ["VizSpec", "FinalResponse", "Provenance"]
