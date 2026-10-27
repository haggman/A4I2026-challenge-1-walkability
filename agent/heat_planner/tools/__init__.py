"""Custom Python function tools for the Atlanta Urban Heat Planning Assistant."""

from .audit import run_equity_audit
from .demographics import get_area_demographics, get_walkable_demographics
from .heat_model import compare_sites, explain_heat_offset, rank_candidate_sites
from .history import get_heat_frequency
from .location import (
    build_google_maps_urls,
    infer_atlanta_neighborhood,
    resolve_atlanta_location,
    resolve_location,
)
from .recommendation import assemble_placement_recommendation

__all__ = [
    "resolve_atlanta_location",
    "resolve_location",
    "build_google_maps_urls",
    "infer_atlanta_neighborhood",
    "explain_heat_offset",
    "rank_candidate_sites",
    "compare_sites",
    "get_heat_frequency",
    "get_walkable_demographics",
    "get_area_demographics",
    "run_equity_audit",
    "assemble_placement_recommendation",
]
