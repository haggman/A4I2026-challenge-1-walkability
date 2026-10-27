"""Tool I/O contracts. The PlacementRecommendation is also the front-end contract.

Front end mocks against PlacementRecommendation.model_json_schema() from minute zero,
so changing a field here is a cross-lane change: announce it.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["ok", "no_data", "out_of_scope", "error"]


class ToolResult(BaseModel):
    status: Status = "ok"
    error_message: str | None = None


class Driver(BaseModel):
    feature: str
    label: str = Field(description="Planner-readable name, e.g. 'housing density within 1.5 km'")
    attribution_f: float = Field(description="°F this feature adds (+) or removes (−) vs. baseline")


class HeatExplanation(ToolResult):
    lat: float | None = None
    lon: float | None = None
    geo_id: str | None = None
    predicted_offset_f: float | None = None
    baseline_offset_f: float | None = None
    drivers: list[Driver] = []
    forecast_high_f: float | None = None
    implied_local_high_f: float | None = None
    measured_nearby: bool | None = None
    summary: str | None = None
    model_version: str | None = None


class Demographics(ToolResult):
    geo_id: str | None = None
    total_pop: float | None = None
    median_age: float | None = None
    median_income: float | None = None
    poverty_rate: float | None = None
    no_vehicle_rate: float | None = None
    city_comparison: dict[str, float] = {}


class SiteAssessment(BaseModel):
    rank: int
    site_id: str
    lat: float
    lon: float
    address_hint: str | None = None
    predicted_offset_f: float
    drivers: list[Driver]
    demographics: Demographics
    score: float
    why: str = Field(description="One sentence a dispatcher or council member can read")


class EquityAudit(ToolResult):
    n_sites: int = 0
    comparisons: dict[str, dict[str, float]] = {}   # metric → {sites, city, ratio}
    finding: str | None = None


class PlacementRecommendation(ToolResult):
    city: str
    track: str
    scenario: str
    forecast_high_f: float | None = None
    sites: list[SiteAssessment] = []
    heat_frequency: dict | None = None
    equity_audit: EquityAudit | None = None
    limitations: list[str] = []
    model_version: str | None = None
    generated_at: str | None = None
