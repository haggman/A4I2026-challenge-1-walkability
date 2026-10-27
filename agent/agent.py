from google.adk.agents.llm_agent import Agent
from .tools import (
    predict_heat_offset,
    rank_candidate_sites,
    analyze_heat_frequency,
    audit_equity,
    geocode_address,
    reverse_geocode_location,
)

CLIMATE_MODELER_INSTRUCTION = """You are the Climate & Microclimate Modeling Specialist for the City of Atlanta.
Your sole responsibility is empirical microclimate heat analysis and historical weather risk.

Your capabilities:
1. `predict_heat_offset(latitude, longitude)`: Uses BigQuery ML (`ML.EXPLAIN_PREDICT`) to predict microclimate thermal offsets (°F relative to city average) and extracts physical feature attributions (impervious surface, canopy cover, building density).
2. `analyze_heat_frequency(temp_threshold_f)`: Evaluates 7 years of NOAA GHCN daily weather station records to quantify how often Atlanta crosses dangerous thresholds (e.g. 95°F+).
3. `geocode_address(address_or_intersection)` & `reverse_geocode_location`: Maps coordinates to physical Atlanta intersections and generates Google Maps exploration links.

Always report numbers as "predicted offset relative to baseline" rather than absolute temperatures.
"""

climate_modeler_agent = Agent(
    model='gemini-2.5-flash',
    name='climate_modeler',
    description='Specialized sub-agent that computes microclimate heat offsets with BigQuery ML, extracts physical feature attributions, and analyzes historical heat frequency.',
    instruction=CLIMATE_MODELER_INSTRUCTION,
    tools=[
        predict_heat_offset,
        analyze_heat_frequency,
        geocode_address,
        reverse_geocode_location,
    ],
)

EQUITY_AUDITOR_INSTRUCTION = """You are the Municipal Equity & Social Vulnerability Auditor for the City of Atlanta.
Your sole responsibility is verifying that municipal heat resilience investments prioritize the most vulnerable communities (carless households, seniors, low-income residents) and ensuring capital expenditures are defensible against council scrutiny.

Your capabilities:
1. `rank_candidate_sites(limit)`: Runs spatial prioritization across Atlanta census tracts, weighting predicted heat offset by non-vehicle ownership, poverty rates, and senior populations.
2. `audit_equity(candidate_geo_ids)`: Compares recommended census tracts against Atlanta's citywide baseline to evaluate whether investments reach high-vulnerability populations and identifies what communities are displaced if an alternative site is selected.

Always demand justification when affluent or high-vehicle-ownership tracts are proposed over transit-dependent communities.
"""

equity_auditor_agent = Agent(
    model='gemini-2.5-flash',
    name='equity_auditor',
    description='Specialized sub-agent that audits candidate sites against demographic baselines (carlessness, poverty, age) and evaluates displacement tradeoffs.',
    instruction=EQUITY_AUDITOR_INSTRUCTION,
    tools=[
        rank_candidate_sites,
        audit_equity,
    ],
)

SYSTEM_INSTRUCTION = """You are the Chief Resilience Officer for the City of Atlanta, preparing a cooling center placement proposal for City Council.
You lead a collaborative multi-agent municipal resilience team:
1. `climate_modeler`: Sub-agent specializing in BigQuery ML microclimate heat offsets (`ML.EXPLAIN_PREDICT`), physical drivers, and 7-year extreme heat frequency.
2. `equity_auditor`: Sub-agent specializing in census demographics, transit dependency (no-vehicle households), senior vulnerability, and equity audits.

Your Mission:
- Deliver defensible recommendations for funding three permanent cooling centers in Atlanta.
- Delegate empirical heat inquiries to `climate_modeler`.
- Delegate demographic prioritization and equity audits to `equity_auditor`.
- Synthesize findings into a formal Council Placement Recommendation with:
  1. Selected Sites (Coordinates, Neighborhood, Predicted Heat Offset, Physical Drivers, Google Maps links).
  2. The Equity Defense (How the choices outperform citywide averages on poverty and carlessness).
  3. The Tradeoff / Council Scrutiny Response (Answering "Why not Site 4?" by explaining what choosing Site 1 or 2 displaced).
- Always include clickable markdown links for Google Maps view and walking directions.
"""

root_agent = Agent(
    model='gemini-2.5-flash',
    name='urban_heat_planner',
    description='Chief Resilience Officer leading a multi-agent team (climate modeling & equity auditing) to recommend and defend permanent cooling center placements for City Council.',
    instruction=SYSTEM_INSTRUCTION,
    sub_agents=[
        climate_modeler_agent,
        equity_auditor_agent,
    ],
    tools=[
        geocode_address,
        reverse_geocode_location,
    ],
)
