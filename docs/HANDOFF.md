# Cross-Lane Data Handoff (`qwiklabs-gcp-04-ec3596addc43`)

## Architecture & Golden Rule for ML and Agent Lanes

- **GCP Project:** `qwiklabs-gcp-04-ec3596addc43` (Location: `US` multi-region)
- **City & Track:** Atlanta, GA · *This budget cycle* (3 permanent cooling centers, council in 3 weeks)
- **Golden Rule:** **Do NOT query raw `a4i_climate` directly from ML models, MCP Toolbox `tools.yaml`, or ADK Python tools.**
  - Raw `a4i_climate` contains 56 other cities, 7 non-11-char FIPS tracts, `-9999.0` sentinels in `median_year_structure_built` (2 tracts) and `median_income` (3 tracts), `100%` NULL `observed_at` timestamps, and un-weighted 1 Hz road autocorrelation.
  - **ML Lane (`ml-engineer`):** Read exclusively from **`a4i_ml`** (`tracts_enriched`, `campaign_footprint`, `point_features(pts)`) and **`a4i_semantic.fact_heat_cell`** (`spatial_block_id` for spatial block holdout).
  - **Agent & Toolbox Lanes (`agent-engineer`, `mcp-toolbox`):** Read exclusively from **`a4i_semantic`** (`dim_tract`, `fact_heat_cell`, `fact_city_heat_day`, `metric_city_heat_days_by_year`, `site_hot_days(offset_f)`, `vulnerable_population(lat, lon, radius_m)`, `audit_city_baseline`) and **`a4i_ml`** (`point_features(pts)`).

---

## Data Tables, Views & Table-Valued Functions (`a4i_core`, `a4i_semantic`, `a4i_ml`)

### 1. Semantic Layer (`qwiklabs-gcp-04-ec3596addc43.a4i_semantic`) — Primary Contract for Agent & ML

| Semantic Object | Type | Grain | Verified Row Count | What It Is For |
|---|---|---|---:|---|
| `a4i_semantic.dim_tract` | VIEW | 1 row per Atlanta Census tract (`tract_geoid`, 11-char FIPS) | **353** | Planner-facing tract lookup with demographics, ACS 65+ share (`pct_age_65_plus`), TIGER land/water ratio, population/housing density, non-racial `vulnerability_pct` (`[0, 1]`), and `vulnerability_tier` (`1=Lowest .. 4=Highest`). |
| `a4i_semantic.fact_heat_cell` | TABLE | 1 row per `geohash-7` cell (~150 m × 150 m, `cell_id`) | **2,020** (across **22** `geohash-5` blocks) | De-autocorrelated heat cells with `heat_offset_f` (°F above city mean `82.062°F`), `max_heat_offset_f`, `reading_count`, `spatial_block_id` (`geohash-5` ~4.9 km block for leak-free CV split), and assigned `tract_geoid`. |
| `a4i_semantic.fact_city_heat_day` | VIEW | 1 row per calendar date (`observation_date`) | **2,557** (`2019-01-01` to `2025-12-31`) | Daily city-wide reference maximum temperature (`city_max_temp_f`) averaged across reporting Atlanta GHCN stations (`station_count`). |
| `a4i_semantic.metric_city_heat_days_by_year` | VIEW | 1 row per calendar year (`obs_year`, `2019–2025`) | **7** | Annual GHCN station-history summary of heat days (`days_ge_90f`, `days_ge_95f`, `days_ge_100f`, `days_ge_105f`), summer Jun–Aug average daily max, and annual peak temperature. |
| `a4i_semantic.site_hot_days(offset_f FLOAT64)` | TVF | 1 summary row for a candidate site with `+offset_f` °F offset | **1** (per call) | Answers *"How often does this site reach ≥90/95/100/105°F per year?"* by combining the site's predicted `offset_f` with the 7-year GHCN `fact_city_heat_day` curve. |
| `a4i_semantic.vulnerable_population(lat FLOAT64, lon FLOAT64, radius_m FLOAT64)` | TVF | 1 row per Census tract intersecting the `radius_m` catchment circle | Variable (typically **3–8** tracts for `800 m`) | Computes area-weighted population (`est_pop_in_radius`), seniors 65+ (`est_pop_age_65_plus_in_radius`), and zero-vehicle households (`est_no_car_hh_in_radius`) inside a cooling center's walk/transit catchment. |
| `a4i_semantic.audit_city_baseline` | VIEW | 1 row representing the entire Atlanta study area (`CITY_ALL_TRACTS`) | **1** | Population-weighted and household-weighted citywide baseline (`city_poverty_rate = 0.1385`, `city_no_vehicle_rate = 0.1059`, `city_pct_age_65_plus = 0.1190`, `city_median_income = $73,240`) for the post-hoc equity audit. |

### 2. ML Feature Backbone (`qwiklabs-gcp-04-ec3596addc43.a4i_ml`)

| ML Object | Type | Grain | Verified Row Count | What It Is For |
|---|---|---|---:|---|
| `a4i_ml.tracts_enriched` | TABLE | 1 row per Atlanta Census tract (`geo_id`, 11-char FIPS) | **353** | Cleaned tract features + city-median-imputed model-ready `feat_*` columns (`0` NULLs, `0` sentinels, `0` race columns). |
| `a4i_ml.campaign_footprint` | TABLE | 1 row for the Atlanta Heat Watch campaign footprint | **1** | Precomputed `convex_hull_geom`, `footprint_500m_geom` (union of 500 m buffers around all 23,386 readings), and `campaign_mean_f = 82.062°F`. |
| `a4i_ml.point_features(pts ARRAY<STRUCT<point_id STRING, lat FLOAT64, lon FLOAT64>>)` | TVF | 1 row per candidate point `(point_id, lat, lon)` | `ARRAY_LENGTH(pts)` | **Single source of truth for ML feature assembly** at any candidate `(lat, lon)`. Used identically at training time (`fact_heat_cell` centroids) and serving time (`ML.EXPLAIN_PREDICT`). Returns `nearest_reading_m` and `in_footprint` (`TRUE` if within `500 m` of a campaign reading) so the agent refuses out-of-footprint locations honestly. |
| `a4i_ml.train_cells` | TABLE | 1 row per `geohash-7` cell (`n_readings >= 3`) | **1,862** (`1,378` train / `484` eval across `22` `geohash-5` blocks) | Joins `a4i_semantic.fact_heat_cell` with `a4i_ml.point_features` and assigns the `is_eval` `geohash-5` spatial-block holdout split (`sql/ml/02_train.sql`). |
| `a4i_ml.offset_model_v1` | MODEL (`LINEAR_REG`) | Trained BQML model predicting `offset_f` | — | Predicts street-level `offset_f` (°F vs `82.062°F` campaign mean) from physical/built-environment features (`enable_global_explain = TRUE`, `l2_reg = 0.1`); beats predict-zero baseline on held-out spatial blocks (`MAE = 1.254°F` vs `1.355°F`). |
| `a4i_ml.grid_predictions` | TABLE | 1 row per ~250 m grid point inside `campaign_footprint` | **5,618** (`4,502` unmeasured + `1,116` measured across `100` tracts) | Pre-computed `ML.EXPLAIN_PREDICT` scores (`predicted_offset_f`, `top_feature_attributions`) joined with tract vulnerability metrics (`sql/ml/04_serve.sql`) to power `sql/serve/rank_sites.sql`. |

### 3. Cleaned Core Layer (`qwiklabs-gcp-04-ec3596addc43.a4i_core`)

| Core Table | Type | Grain | Verified Row Count | Key Cleaning & Enrichments Applied |
|---|---|---|---:|---|
| `a4i_core.heat_readings` | TABLE | 1 row per cleaned Atlanta Heat Watch traverse reading (`reading_id`) | **23,386** | Filtered to `city = 'Atlanta'`, deduplicated on `(lon, lat, temp_f, heat_index_f, humidity_pct)`, computed `heat_offset_f = temp_f - 82.062`, `spatial_weight` (`1/(1 + neighbors_within_20m)`), `geohash_5`, `geohash_7`, and polygon-matched `tract_geoid`. |
| `a4i_core.station_days` | TABLE | 1 row per GHCN station × calendar day (`station_id`, `observation_date`) | **17,452** | Filtered to 7 stations within 50 km of Atlanta (`33.7490, -84.3880`) and sane `max_temp_f BETWEEN -30 AND 130`; precomputed `is_hot_90f/95f/100f/105f`. |
| `a4i_core.tracts` | TABLE | 1 row per Atlanta Census tract (`geo_id`) | **353** | `LPAD(CAST(geo_id AS STRING), 11, '0')`, sentinel `-9999.0 -> NULL` on `median_income` (3 tracts) and `median_year_structure_built` (2 tracts), rate bounds `[0, 1]`, joined to ACS 2020 5-yr `pop_age_65_plus` (`353/353` match) and US Census TIGER polygons + land/water area (`353/353` match). |

---

## Tool Architecture Recommendation: MCP Toolbox (`tools.yaml`) vs ADK Python Tools

To satisfy Non-Negotiables #2 (*call BQML `ML.EXPLAIN_PREDICT` through a tool we built*), #5 (*consume a managed MCP server*), #6 (*at least one tool we designed*), and #8 (*refuse honestly outside footprint*), expose the semantic and ML layers as follows:

| Capability / Planner Question | Recommended Surface | Underlying BigQuery Object(s) | Why This Surface? |
|---|---|---|---|
| **1. Hottest tracts & neighborhood vulnerability lookup** (*"Which neighborhoods in Atlanta have the highest vulnerability and measured heat offsets?"*) | **MCP Toolbox (`tools.yaml`)** — `list_priority_tracts` / `get_tract_profile` | `a4i_semantic.dim_tract` + `a4i_semantic.fact_heat_cell` | Pure parameterized read-only SQL (`@min_vulnerability_tier`, `@limit`); zero post-processing required; ideal showcase for managed MCP Toolbox for Databases. |
| **2. Historical heat frequency & climate trend** (*"How many 90°F / 95°F / 100°F days does Atlanta get per year, and how many extra hot days does a +4.5°F site experience?"*) | **MCP Toolbox (`tools.yaml`)** — `get_city_heat_frequency` & `get_site_hot_days` | `a4i_semantic.metric_city_heat_days_by_year` & `a4i_semantic.site_hot_days(@offset_f)` | Parameterized TVF call (`SELECT * FROM a4i_semantic.site_hot_days(@offset_f)`) is a clean single-statement SQL query suited for MCP Toolbox. |
| **3. Catchment demographics around a candidate site** (*"Who lives within an 800m walk of (lat, lon)?"*) | **MCP Toolbox (`tools.yaml`)** — `get_catchment_vulnerability` | `a4i_semantic.vulnerable_population(@lat, @lon, @radius_m)` | Single-statement spatial TVF returning both tract-by-tract breakdown and area-weighted totals (`est_pop_in_radius`, `est_pop_age_65_plus_in_radius`, `est_no_car_hh_in_radius`). |
| **4. Predict heat offset & feature attributions at unmeasured `(lat, lon)`** (*"What is the predicted heat offset at this unmeasured park/lot, and why?"*) | **ADK Python Function Tool** — `explain_heat_offset(lat, lon)` | `a4i_ml.point_features([STRUCT('q', @lat, @lon)])` → `ML.EXPLAIN_PREDICT(MODEL a4i_ml.heat_offset_model, ...)` | **Must enforce refusal gate in Python** (`if not row.in_footprint: return RefusalResponse(...)`), format top-k `ML.EXPLAIN_PREDICT` attributions into Pydantic `FeatureDriver` objects, and enforce offset framing (`+X.X°F vs city mean`). |
| **5. Rank candidate cooling center sites & assemble Placement Recommendation** (*"Recommend 3 permanent cooling center sites for council"*) | **ADK Python Function Tool** — `recommend_cooling_centers(...)` | `a4i_ml.grid_predictions` (or batch `ML.EXPLAIN_PREDICT`), `a4i_semantic.vulnerable_population`, `a4i_semantic.site_hot_days` | Requires multi-step orchestration, minimum spacing constraint between the 3 recommended cooling centers (e.g. `>= 1.5 km` apart), and structured Pydantic `PlacementRecommendation` serialization. |
| **6. Post-hoc Equity Audit** (*"Did our 3 recommended sites reach tracts with higher need than the city average?"*) | **ADK Python Function Tool** — `run_equity_audit(tract_geoids)` | `a4i_semantic.dim_tract` compared against `a4i_semantic.audit_city_baseline` (+ ACS race composition in post-hoc output check only) | Takes the dynamic list of recommended `tract_geoids` from session state, compares population-weighted recommended tracts vs `a4i_semantic.audit_city_baseline`, and formats the council-ready audit table. |

---

## Proposed Read-Only Dataset Grants (DCL)

File: [`01_grant_dataviewer.sql`](file:///Users/harika/Documents/AgentsforImpact/A4I2026-challenge-1-walkability/sql/grants/01_grant_dataviewer.sql) (staged; **do not run until `heat-agent-sa` and `toolbox-sa` exist and user approves**):

```sql
GRANT `roles/bigquery.dataViewer`
ON SCHEMA `qwiklabs-gcp-04-ec3596addc43.a4i_core`
TO
  "serviceAccount:heat-agent-sa@qwiklabs-gcp-04-ec3596addc43.iam.gserviceaccount.com",
  "serviceAccount:toolbox-sa@qwiklabs-gcp-04-ec3596addc43.iam.gserviceaccount.com";

GRANT `roles/bigquery.dataViewer`
ON SCHEMA `qwiklabs-gcp-04-ec3596addc43.a4i_semantic`
TO
  "serviceAccount:heat-agent-sa@qwiklabs-gcp-04-ec3596addc43.iam.gserviceaccount.com",
  "serviceAccount:toolbox-sa@qwiklabs-gcp-04-ec3596addc43.iam.gserviceaccount.com";

GRANT `roles/bigquery.dataViewer`
ON SCHEMA `qwiklabs-gcp-04-ec3596addc43.a4i_ml`
TO
  "serviceAccount:heat-agent-sa@qwiklabs-gcp-04-ec3596addc43.iam.gserviceaccount.com",
  "serviceAccount:toolbox-sa@qwiklabs-gcp-04-ec3596addc43.iam.gserviceaccount.com";
```
