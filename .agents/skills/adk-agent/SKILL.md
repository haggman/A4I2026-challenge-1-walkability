---
name: adk-agent
description: Builds the Python ADK (Agent Development Kit) heat-planning agent. It covers project layout, Gemini model config, custom function tools that call the BQML ML.EXPLAIN_PREDICT model, the MCP Toolbox toolset, the system instruction (including refusal behaviour), session state, and adk eval tests. Use when scaffolding or changing the agent, writing or debugging a tool, tuning the prompt, or testing against the seven planner questions.
---

# ADK agent: the heat planning assistant

You are acting as the **agent engineer**. The agent is the product: a planner keeps it open
because it reaches for the right tool, explains *why*, and refuses when it has no basis.

## Layout (in the team repo)

```
agent/
  heat_planner/
    __init__.py          # from . import agent
    agent.py             # root_agent
    config.py            # env → typed settings (model ids, project, model version, toolbox url)
    prompts.py           # SYSTEM_INSTRUCTION (versioned, reviewed like code)
    schemas.py           # Pydantic: ToolResult, Driver, SiteAssessment, PlacementRecommendation
    bq.py                # one BigQuery client, run_query(sql_file, params) with byte cap
    tools/
      location.py        # resolve_location: "4th and Marsalis" / "lat,lon" → point + footprint check
      heat_model.py      # explain_heat_offset, rank_candidate_sites  (wrap BQML)
      history.py         # get_heat_frequency (GHCN)
      demographics.py    # get_area_demographics
      audit.py           # run_equity_audit
      recommendation.py  # assemble_placement_recommendation (stores in session state)
    sql/                 # copies of the data lane's serve SQL, parameterized
  tests/
    test_tools.py        # unit, BigQuery mocked
    planner.evalset.json # adk eval: 7 planner questions + refusal cases
  requirements.txt       # pinned
  .env.example
```

Reference implementations are in `examples/`. Copy, then adapt names to what the data lane actually built.

## Setup (Cloud Shell)

```bash
cd agent && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # google-adk, google-cloud-bigquery, pydantic, httpx (pinned)
cp .env.example heat_planner/.env        # fill in project; GOOGLE_GENAI_USE_VERTEXAI=TRUE
adk web --port 8080                      # Cloud Shell: Web Preview → port 8080
```
Confirm the current GA Gemini model IDs on the Gemini platform before pinning them in
`.env` (`AGENT_MODEL` for the fast loop, `WRITER_MODEL` for proposal drafting). Don't hardcode
model IDs in code. Check the installed ADK version (`pip show google-adk`) and match import
paths to its docs. MCP imports in particular have moved between releases.

## Tool design principles (this is what "a tool you built" is judged on)

1. **Tools do the shaping; the LLM does the judgment.** Turning a place name into a point,
   nested attributions into "+4.2 °F from dense housing", four sources into one recommendation:
   all in Python, deterministic, and unit-tested.
2. **Typed, small, composable.** Primitive params, Pydantic outputs, `status` on every result.
3. **Fail as data, not exceptions.** `out_of_scope` (outside footprint / other city),
   `no_data`, `error` each come with a sentence the model can say to the planner.
4. **Cheap and bounded.** `maximum_bytes_billed`, query timeout, ranking reads the precomputed
   `grid_predictions` table, so only ad-hoc points hit `ML.EXPLAIN_PREDICT` live.
5. **State over re-asking.** Store the last ranked sites and recommendation in
   `tool_context.state` so "draft the proposal" and "audit it" operate on what was just shown.

### Tool ↔ planner-question map

| Planner question | Tool(s) | Source |
|---|---|---|
| Where should 3 cooling centers go? | `rank_candidate_sites` | `grid_predictions` (BQML) + demographics |
| Why is X worse than 2 blocks north? | `resolve_location` ×2 → `explain_heat_offset` ×2 | `ML.EXPLAIN_PREDICT` live |
| How often does it hit dangerous heat? Worse? | `get_heat_frequency` | GHCN station history |
| Who lives around that site? | `get_area_demographics` | ACS tracts |
| Make the case for A vs B | `explain_heat_offset` + `get_area_demographics` → Gemini reasons | both |
| Draft the council proposal | `assemble_placement_recommendation` → Gemini writes | all |
| Did we reach those who need it most? | `run_equity_audit` | output vs city, pop-weighted |
| Anything generic ("how many tracts…") | MCP Toolbox toolset (read-only) | BigQuery |

## MCP: consume, don't author

Connect the team's MCP Toolbox service (see `/mcp-toolbox`) as a toolset:
`examples/agent.py` shows `McpToolset` over Streamable HTTP with an ID-token header for a
private Cloud Run service. Keep generic SQL tools **read-only** and scoped to `a4i_climate` /
`a4i_ml`. If the Toolbox isn't up yet, the agent must still start, so wrap the connection in a
feature flag (`TOOLBOX_URL` empty → skip).

## System instruction

`examples/prompts.py` is the starting point. It must cover: who the user is, the track and city,
offset language, tool routing, when to ask a clarifying question (once, briefly), **when to
refuse**, citation of numbers to tools, and output format for recommendations. Treat changes as
code: one change → re-run the eval set.

## Testing

- `pytest agent/tests -m "not live"` runs on every commit (mocked BigQuery).
- `adk eval agent/heat_planner agent/tests/planner.evalset.json` runs before every deploy. The
  eval checks tool trajectory (did it *call* `explain_heat_offset`?) and response shape.
- Manual: ask all seven planner questions in `adk web`, plus the refusal set:
  other city · point in a lake/outside footprint · "what will the offset be after we plant
  200 trees?" (can't simulate the fix: say so) · "what will the temperature be at 3pm Thursday?"
  (forecast high + offset, labelled as an estimate) · request to rank by race (decline, explain
  audit-only use).

## Definition of done (agent lane)

- [ ] `root_agent` answers all 7 planner questions with tool calls, and the refusal set refuses.
- [ ] At least one designed tool calls `ML.EXPLAIN_PREDICT`; at least one MCP toolset consumed.
- [ ] Unit tests green; eval set passes; deployed URL answers (see `/gcp-platform`).
- [ ] Every number in a response traces to a tool result (no invented figures).
