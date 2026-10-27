# Reference implementations

| File | Goes to | Notes |
|---|---|---|
| `config.py`, `schemas.py`, `bq.py`, `prompts.py`, `agent.py` | `agent/heat_planner/` | complete |
| `heat_model.py` | `agent/heat_planner/tools/` | complete: the required BQML tool |
| `rank_sites.sql` | `agent/heat_planner/sql/` | plus the data lane's `explain_point.sql` |
| `planner.evalset.json` | `agent/tests/` | regenerate in ADK's schema from `adk web` → Eval if needed |
| `env.example`, `requirements.txt` | `agent/` | pin versions at kickoff |

The remaining tools follow the same pattern as `heat_model.py` (docstring written for the model,
primitive params, Pydantic result with `status`, `bq.run(...)` with a named SQL file, write to
`tool_context.state` when later turns need the result):

- `location.resolve_location(place: str)`: accepts `"lat, lon"` directly. Otherwise calls the
  Google Maps Geocoding API (biased to the city bounds) when `MAPS_API_KEY` is set. Then checks
  `campaign_footprint` and returns `out_of_scope` outside it. Without a key, returns `no_data`
  asking for coordinates or a listed landmark.
- `history.get_heat_frequency()` wraps `heat-data/resources/heat_frequency.sql`.
- `demographics.get_area_demographics(lat, lon)` wraps `nearest_tract.sql`, plus population-weighted
  city averages for comparison.
- `audit.run_equity_audit(site_ids: list[str] = [])` defaults to `state["last_ranked_sites"]`. See `/equity-audit`.
- `recommendation.assemble_placement_recommendation(scenario: str, forecast_high_f: float = 0)`
  builds a `PlacementRecommendation` from state + frequency + audit, stores it in
  `state["placement_recommendation"]`, and returns it. See `/placement-recommendation`.
