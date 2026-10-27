---
trigger: glob
globs: "**/*.sql, toolbox/**/*.yaml"
description: BigQuery SQL conventions and data traps for the heat challenge.
---

# BigQuery SQL conventions

- Standard SQL only. Fully qualify tables as `` `${PROJECT}.a4i_climate.table` `` in anything
  deployed. Unqualified `dataset.table` is fine only in notebooks.
- Header comment on every file: purpose, inputs, outputs, owner lane, and *why* for non-obvious steps.
- Parameters are named (`@lat`, `@lon`, `@k`). No string concatenation of inputs.
- `SAFE_CAST` anything from `bigquery-public-data`. `LPAD(geo_id, 11, '0')` on every ACS join.
- Use `SAFE_DIVIDE` for rates. Use `ST_GEOGPOINT(lon, lat)` (**longitude first**) and
  `ST_DISTANCE` in meters.
- Never select `temp_f`, `heat_index_f`, `humidity_pct` or `observed_at` into a feature view.
  They are label-side or drive-day measurements.
- Never select race/ethnicity columns into a feature view or a model. They are allowed only in
  `sql/audit/`.
- Feature views are `CREATE OR REPLACE VIEW`. Models are versioned (`offset_model_v1`, `_v2`)
  rather than overwritten, so the agent lane is never broken mid-demo. `offset_model` is a
  stable alias view or config value pointing at the promoted version.
- Prefer `ML.EXPLAIN_PREDICT(..., STRUCT(5 AS top_k_features))` over `ML.PREDICT` in any path
  the agent calls.
