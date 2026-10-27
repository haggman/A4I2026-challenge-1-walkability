---
name: placement-recommendation
description: Defines and produces the Placement Recommendation, the challenge's required output artifact. It's a ranked list of sites with coordinates, predicted heat offset, the ML.EXPLAIN_PREDICT drivers, who lives there, heat frequency, an equity audit, limitations, and a council-ready drafted proposal. Use when building the assemble tool, rendering the artifact for the UI or deck, or writing the proposal prose.
---

# Placement Recommendation (the output artifact)

It's the thing a planner actually *receives*, not a console dump. The JSON contract is
`PlacementRecommendation` in `adk-agent/examples/schemas.py`. The front end and deck render it.

## Contract-first (why this matters for the team)

The schema is frozen early in Build so the **front end mocks against it** while the agent is
still being written. Commit `docs/contracts/placement_recommendation.schema.json`
(`PlacementRecommendation.model_json_schema()`) and `docs/contracts/sample.json` (a realistic
filled example). Changing a field is a cross-lane change: announce it.

## Required content, per site

| Field | Example | Source |
|---|---|---|
| Rank + coordinates "specific enough to stand on" | `32.7462, -96.7981` (+ address hint if geocoded) | grid / geocoder |
| Predicted offset | `+6.8 °F vs. city average` | BQML |
| Why (top drivers, °F) | `+3.1 dense housing within 1.5 km · +1.9 pre-1960 buildings` | `ML.EXPLAIN_PREDICT` |
| Who lives there | `4,210 people · 31% no car · median age 41 · 28% poverty` | ACS |
| One-line reason | written for a dispatcher / council member | tool |

Plus, once per recommendation: scenario, forecast (if given), heat frequency (days ≥95 °F/yr),
equity audit summary, **limitations**, model version, timestamp.

## Track variants

- **Today:** 5–10 stops, ordered for a dispatcher, `no_vehicle_rate` and age weighted, "reach
  people who can't leave". Output reads like a run sheet.
- **This budget cycle:** 3–4 permanent sites, each paired with heat frequency; cost and what it
  displaces if known; survives a council meeting.
- **This decade:** neighbourhood-scale program; for each area the **dominant driver** →
  intervention (impervious → cool pavement; density/no canopy → trees/open space). State
  plainly that the fix can't be simulated.

## Proposal prose (Gemini writes; tools supply every number)

Structure (≤ 1 page): **Decision requested** → **Recommended sites** (table) → **Why these
places** (drivers in plain words) → **Who benefits** → **How often this heat happens** →
**Equity check** → **Cost / trade-offs** (if known; otherwise say "not estimated") →
**Limitations** → **Data sources & credits** (NOAA/CAPA Heat Watch, NOAA GHCN-Daily, US Census ACS).

Use the `WRITER_MODEL` for this step if latency allows. Instruct it: "Use only numbers present
in the JSON. If a value is missing, say it is not available."

## Standard limitations block (adapt, don't delete)

- Street-level heat is one afternoon campaign driven by volunteers. It shows the spatial
  pattern, not a forecast or a climatology.
- Offsets are relative to the city average on that day. Absolute temperatures shown are
  forecast + offset estimates.
- Demographics are census-tract averages (ACS 5-year), assigned by nearest tract centroid.
- Distances are straight-line, not walking routes.
- The model identifies drivers; it can't simulate the effect of an intervention.
- Race was excluded from the model and used only in the post-hoc equity audit.
