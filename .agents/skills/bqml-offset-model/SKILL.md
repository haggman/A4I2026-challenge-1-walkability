---
name: bqml-offset-model
description: Designs, trains, evaluates and serves the BigQuery ML heat-offset model (°F above city mean) with ML.EXPLAIN_PREDICT attributions. Use when engineering features, creating or versioning the model, hunting leakage, evaluating against a baseline, building the candidate-site prediction grid, or writing the exact SQL the agent's prediction tool wraps.
---

# BQML heat-offset model

You are acting as the **ML engineer** on the data lane. BigQuery ML is this challenge's required
differentiator. The model must predict for **places nobody measured**, and explain *why*.

## Design in one picture

```
heat_observations ──► train_cells (≈150 m geohash cells, label = cell mean − city mean)
                            │
tract_demographics ─► tracts_enriched ─┐
                                       ├─► point_features(pts)  ◄── ONE feature function,
campaign_footprint ────────────────────┘        │                    used for train AND serve
                                                 │                   (no training/serving skew)
                     ┌───────────────────────────┼─────────────────────────────┐
                     ▼                           ▼                             ▼
          offset_model_vN (LINEAR_REG)   grid_predictions (batch)      explain_point (online)
          spatial-block eval split       ~250 m candidate grid          any lat/lon the
          ML.EVALUATE vs. zero baseline  + attributions + demographics  planner names
                                         → rank_sites tool              → explain_heat_offset tool
```

Hazard (the offset model) is kept separate from vulnerability (demographics used in ranking).
Risk = hazard × exposure × vulnerability (the IPCC framing), so say it that way in the deck.
Socioeconomic variables are **not** model features by default. They weight the ranking.
That keeps attributions physical ("older housing stock, dense core") and defensible.

## Steps (files in `resources/`, replace `PROJECT`)

0. `bq --location=US mk -d PROJECT:a4i_ml` (separate from `a4i_climate`, so `load.sh` can't clobber it).
1. **`01_features.sql`** creates `tracts_enriched` (adds land area → densities), `campaign_footprint`
   (buffered hull of the drive routes), and the table function `point_features(pts)`.
2. **`02_train.sql`** creates `train_cells` and `offset_model_v1`.
3. **`03_evaluate.sql`** runs `ML.EVALUATE` vs. a predict-zero baseline, per-split residuals, and `ML.GLOBAL_EXPLAIN`.
4. **`04_serve.sql`** creates the `explain_point` query (the agent tool's SQL) and the `grid_predictions` table.

Run each with `bq query --use_legacy_sql=false < file.sql` after substitution, or paste into the
console. Record row counts and metrics in `docs/DECISIONS.md`.

## Why each design choice (judges will ask; this is the Rigor score)

| Choice | Why | Rejected alternative |
|---|---|---|
| Label = offset from campaign mean | Readings share a 1-hour window, so the difference is purely spatial and the model can't learn the calendar | Absolute temp: learns "summer is hot", useless |
| Aggregate to ~150 m cells | 1 Hz readings along a road are near-duplicates. Cells reduce noise and autocorrelation | Raw points: inflated n, leaky |
| **Spatial block split** (geohash-5 ≈ 5 km blocks → 20% eval) | Neighbouring cells share heat. A random split tests memorization, not generalization to unmeasured areas | Random split: optimistic metrics |
| Never use temp/heat index/humidity/observed_at as features | Drive-day measurements don't exist at unmeasured points (leakage) | — |
| `LINEAR_REG` | Free tier, trains in seconds, attributions are exact and legible | Boosted tree: bills through Gemini platform, more fit, less legible; try as v2 only if time allows, as a decision |
| Raw lat/lon excluded | Attributions like "latitude +2°F" mean nothing to a planner, and invite memorization | — |
| Footprint gate | Model is only trustworthy inside (buffered) campaign coverage | Silent extrapolation |

## Sanity bars (if you see these, stop)

- Eval R² > 0.9 or MAE ≈ 0 → leakage. Find the feature that contains the answer.
- Model MAE not better than the predict-zero baseline → features carry no signal. Say so and add
  built-environment data (EPA SLD, canopy) rather than tuning.
- Honest expectations: with tract-level features, a spatial-holdout R² of ~0.2–0.5 is a *real*
  result. Report it with the baseline comparison.

## Feature backlog (Differentiate phase, in priority order)

1. **EPA Smart Location DB** (CC0, block group): `D3B` intersection density, `D2A_EPHHM` land-use
   mix, `NatWalkInd`. Join via block-group centroid nearest-neighbour. Finer than tracts.
2. **Canopy**: NYC `new_york_trees.tree_census_2015` → trees within 200 m; other cities: city
   tree inventory (check license). Usually the most explanatory feature, and it powers the decade track.
3. **Impervious surface** / land-cover layer if the city publishes one (check license).
4. Water/park proximity from city open data (**not OSM**: ODbL).

Each addition is a new version (`offset_model_v2`…). Compare on the **same** spatial split. Keep
`v1` until `v2` is proven, then promote it by updating `MODEL_ID` in the agent config. Never
replace a model the agent is calling mid-demo.

## Hand-off to the agent lane (do this within ~20 min of the first model)

Commit `sql/serve/explain_point.sql` and post: model id, feature list, eval MAE vs baseline,
an example call result for one measured point and one unmeasured point.

## Translating attributions for humans

`top_feature_attributions` is `ARRAY<STRUCT<feature STRING, attribution FLOAT64>>` relative to
`baseline_prediction_value`. Map feature names → planner language in the tool (see
`/adk-agent`, `FEATURE_LABELS`). Example rendering:
"+3.1 °F from dense housing within 1.5 km, +1.4 °F from pre-1960 housing stock, −0.8 °F from
distance to the urban core."
