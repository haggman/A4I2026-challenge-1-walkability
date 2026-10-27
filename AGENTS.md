# AGENTS.md: A4I 2026 Challenge 1 (Urban Heat Planning Assistant)

Antigravity loads this file into every turn for this workspace. Keep it short. Detailed how-to
lives in `.agents/skills/` (loaded on demand). Lane specialists live in `.agents/agents/`.

## Mission

Build a **planning assistant for one city's heat response**: an ADK agent, running on Google
Cloud, that a city planner can hold a working conversation with. It reaches for real data in
BigQuery and a real **BigQuery ML** model to answer *"where should help go, and why?"* for
locations nobody measured. The headline output is the **Placement Recommendation**.

Source of truth for the challenge is the cloned challenge repo `README.md` and
`notebooks/c1_01_load_explore.ipynb`. If this file and those ever disagree, they win. Say so.

## Team decisions (fill these in during kickoff, then never change them silently)

| Decision | Value |
|---|---|
| City | `Atlanta, GA` |
| Track | `This budget cycle` (3 permanent cooling centers, council in 3 weeks) |
| Scenario (one sentence) | `"We're the City of Atlanta, July, 3 permanent cooling centers, council in 3 weeks"` |
| GCP project | `qwiklabs-gcp-04-ec3596addc43` |
| Region (compute) | `us-central1` |
| BigQuery location | `US` (multi-region, matches `scripts/load.sh`) |
| Front end | `heat-ui custom front end`: interactive municipal scenario comparisons, heat-offset choropleth map, and council equity scorecard |
| Deploy target | `Cloud Run` |

## Non-negotiables (judges check these; break none of them)

1. **Predict the offset, not the temperature.** The label is "°F above this city's campaign
   mean". Never phrase output as "it will be 106° here". Say "runs +8°F hotter than the city
   average; with a 102°F forecast that implies ~110°F."
2. **The agent must *call* the BQML model**: `ML.EXPLAIN_PREDICT`, through a tool we built.
   Describing historical rows is not a prediction.
3. **Heat Watch = where. GHCN station history = how often.** Never use one to answer the other.
   Heat Watch is a single afternoon; `observed_at` may be entirely NULL, which is expected.
4. **Race/ethnicity is never a model input.** It may appear only in the post-hoc equity audit
   of our *output*. Do not use CDC SVI `RPL_THEMES` or NYC HVI composite scores as features.
5. **Consume at least one managed MCP server** (MCP Toolbox for Databases or BigQuery's
   managed MCP). Don't author an MCP server from scratch.
6. **At least one tool we designed**: a Python function tool or a Toolbox tool we defined.
7. **Deployed on Google Cloud**: Agent Runtime or Cloud Run. It must actually run there.
8. **Refuse honestly.** If the model has no basis (outside the campaign footprint, another
   city, a "what if we plant trees" simulation), the agent says so. It does not guess.
9. **Data licensing:** public domain / CC0 / US Gov only. No NC, ND, share-alike (ODbL: so
   **no OpenStreetMap-derived data**), no individual-level data, no unstated licenses.

## Data facts that bite (verified in the notebook)

- Dataset `a4i_climate`: `heat_observations(longitude, latitude, city, temp_f, heat_index_f,
  humidity_pct, observed_at)`, `station_daily_temps(station_id, station_name, latitude,
  longitude, observation_date, max_temp_f)`, `tract_demographics(geo_id, tract_lat, tract_lon,
  total_pop, median_age, median_income, housing_units, median_year_structure_built, no_cars,
  households, poverty_rate, no_vehicle_rate)`.
- ACS `geo_id` loses leading zeros for AL, AK, AZ, AR, CA, CO, CT → always `LPAD(geo_id,11,'0')`.
- `geo_census_tracts.internal_point_lat/lon` are STRING → always `SAFE_CAST`.
- Sentinels `-9999`, `-999`, `9999.9` exist in public data; check `MIN()` before trusting a column.
- `temp_f`, `heat_index_f`, `humidity_pct` are **measured on the drive day**. They don't exist
  for unmeasured locations and **must never be features** (that's leakage).
- Readings are spatially autocorrelated (1 Hz along a road). A random train/eval split leaks.
  Use a **spatial block split**. R² near 0.98 means a bug, not a breakthrough.

## Engineering standards

- **Python 3.11+, `google-adk`**, type hints, Pydantic models for every tool I/O and for the
  Placement Recommendation. Tools return structured dicts (`status`, data, `error_message`).
  They never raise into the LLM.
- **SQL lives in `sql/` files**, parameterized (`@lat`, `@lon`), never string-formatted with
  user input. Fully qualify `project.dataset.table` in deployed code.
- **No secrets in git.** Config via env vars and `.env` (gitignored); deployed secrets via
  Secret Manager. No service-account key files. Use ADC and attached service accounts.
- **Least privilege:** dedicated service accounts per runtime (`heat-agent-sa`, `toolbox-sa`),
  dataset-level BigQuery roles, not project Owner.
- **Idempotent infra scripts** in `infra/` (`gcloud` with `--quiet`, existence checks). Every
  resource is labeled `team=<team>,app=heat-planner,env=hackathon`.
- **Pin versions** (ADK, Toolbox image tag, Python deps). No `:latest` in deploy commands.
- **Cost:** prefer `LINEAR_REG` (free tier). `BOOSTED_TREE_*`/`DNN_*`/`AUTOML_*` bill through
  the Gemini platform; choose them deliberately and record why. Glance at bytes processed.
- **Git:** one branch per lane (`data`, `agent`, `frontend`, `story`). Small commits, merge to
  `main` early when another lane is blocked. Never force-push `main`.
- **Shared project:** one GCP project for the whole team. Before creating or deleting any
  resource, check it doesn't already exist and isn't someone else's. Ask before destructive ops
  (`bq rm`, `gcloud ... delete`, `DROP`, `CREATE OR REPLACE` on another lane's object).

## How to work in this repo (for the coding agent)

- Read the relevant skill before acting: `/heat-data`, `/bqml-offset-model`, `/adk-agent`,
  `/mcp-toolbox`, `/gcp-platform`, `/placement-recommendation`, `/equity-audit`,
  `/frontend-ui`, `/pitch-story`, `/judge-review`.
- Verify before you claim. Run the query, run the test, curl the endpoint. Report the actual
  output, including failures.
- Before writing a table/model name from memory, check it exists (`INFORMATION_SCHEMA`, `bq ls`).
- Prefer the smallest change that unblocks another lane. The 4.5-hour clock is the main constraint.
- When you make a design decision a judge could ask about, append one line to
  `docs/DECISIONS.md`: *decision · alternatives · why*. That file feeds the deck.
