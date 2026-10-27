# Created BigQuery Objects (`qwiklabs-gcp-04-ec3596addc43`)

## Stage 1: Core Layer (`a4i_core`)

| Object (`a4i_core.*`) | Type & Rows | Description | How It Can Be Used (1-Line) |
|---|---|---|---|
| `a4i_core.heat_readings` | Table (`23,386` rows) | Cleaned 1 Hz Heat Watch traverse readings (`40–140 °F`) with `city = 'Atlanta'`, `geohash-7` `cell_id`, and reversible boolean flags (`is_stationary_cluster`, `is_temp_outlier`). | Base reading-level table for spatial aggregation into heat cells and campaign footprint polygons. |
| `a4i_core.station_days` | Table (`17,452` rows) | Deduplicated daily max temperatures (`max_temp_f`) across `8` Atlanta GHCN stations (`2019–2025`) with distance (`km`) to the campaign centroid (`11.1–39.4 km`). | Base station-day history used to compute daily city maximum temperatures and multi-year heat frequency. |
| `a4i_core.tracts` | Table (`353` rows) | Sentinel-cleaned (`-666666666` → `NULL`) Atlanta census tracts joined (`100%` match) with ACS 2020 `65+` population (`pop_65_plus`, `share_65_plus`) and TIGER land/water densities (`pop_density_km2`, `housing_density_km2`, `water_share`); zero race columns. | Cleaned tract foundation feeding the semantic tract view, ML feature layer, coverage TVF, and equity audit baseline. |

---

## Stage 2: Semantic Layer (`a4i_semantic`)

| Object (`a4i_semantic.*`) | Type & Rows | Description | How It Can Be Used (1-Line) |
|---|---|---|---|
| `a4i_semantic.dim_tract` | View (`353` rows) | Business-named census tract dimension (`population`, `pop_65_plus`, `share_65_plus`, `car_free_households`, `no_vehicle_rate`, `poverty_rate`, `median_income`, `median_age`, `median_year_built`, densities); no race columns. | Expose via MCP Toolbox / agent tools to look up who lives in any tract and weight candidate cooling-center sites by vulnerability. |
| `a4i_semantic.fact_heat_cell` | View (`2,020` rows) | `~150 m` (`geohash-7`) cells aggregating non-outlier traverse readings with `offset_f` (`cell_mean - campaign_mean`, `-4.23` to `+4.71 °F`), `geohash-5` `block_id`, and `nearest_geo_id`. | Supplies the `offset_f` training labels and `geohash-5` spatial blocks for `a4i_ml.train_cells` and answers where measured heat is highest. |
| `a4i_semantic.fact_city_heat_day` | View (`2,557` rows) | One row per calendar date (`2019–2025`) with `city_max_temp_f` (`MAX(max_temp_f)` across reporting Atlanta GHCN stations). | Daily city temperature series backing annual hot-day counts and site-specific hot-day frequency calculations. |
| `a4i_semantic.metric_city_heat_days_by_year` | View (`7` rows) | Annual hot-day counts (`>= 90 °F`, `>= 95 °F`, `>= 100 °F`) for full years (`>= 300` days), multi-year means (`78.0` / `23.9` / `1.6` days/yr), and OLS slope (`-0.21` days/yr). | Powers the agent's `get_heat_frequency` tool and the pitch deck chart answering *"how often does Atlanta get this hot?"* |
| `a4i_semantic.site_hot_days(offset_f)` | TVF (`1` row) | Table-valued function returning mean annual days (`2019–2025`) where `city_max_temp_f >= 95 - offset_f` compared against the city baseline (`23.9` days/yr). | Translates a site's predicted `+offset_f` into council-ready frequency (e.g., `+3.5 °F` offset = `56.0` days/yr of `95 °F`-equivalent heat vs. `23.9` city-wide). |
| `a4i_semantic.vulnerable_population(lat, lon, radius_m)` | TVF (`1` row) | Table-valued function summing `car_free_households`, `pop_65_plus`, and `population` for tracts whose centroid lies within `radius_m` meters of `(lat, lon)`. | Ranks candidate cooling-center locations by how many seniors (`65+`) and car-free households live within walking/service radius. |
| `a4i_semantic.audit_city_baseline` | View (`1` row) | Population-weighted city baseline across `350` populated tracts (`$75,714` median income, `13.95%` poverty, `8.23%` no-vehicle, `12.47%` age `65+`, `37.02` median age). | Provides the sentinel-free city denominator for `run_equity_audit` to verify recommended sites reach higher-need neighborhoods than the city average. |

---

## Stage 4: ML & Serving Layer (`a4i_ml`)

| Object (`a4i_ml.*`) | Type & Rows | Description | How It Can Be Used (1-Line) |
|---|---|---|---|
| `a4i_ml.tracts_enriched` | Table (`353` rows) | Sentinel-cleaned Atlanta tracts joined with TIGER land/water geometry and ACS 2020 `pop_65_plus`; zero race columns. | Supplies neighborhood physical proxies and post-prediction vulnerability columns for `point_features()` and `grid_predictions`. |
| `a4i_ml.campaign_footprint` | Table (`1` row) | Campaign centroid (`33.7572, -84.3833`), mean temperature (`82.062 °F`), bounding box, and convex hull buffered by `1.5 km`. | Bounds the ~250 m candidate grid (`5,618` points) to prevent out-of-hull geographic extrapolation. |
| `a4i_ml.point_features(pts)` | TVF | Computes physical/built-environment features (`pop_density_km2`, `housing_density_km2`, `water_share`, `median_year_built`, `pop_within_1500m`, `housing_within_1500m`, `km_from_center`, `lat_centered`, `lon_centered`) for any `(point_id, lat, lon)` table. | Shared feature extractor guaranteeing train/serve parity between `train_cells`, `grid_predictions`, and on-demand `ML.EXPLAIN_PREDICT`. |
| `a4i_ml.train_cells` | Table (`1,862` rows) | `geohash-7` cells (`n_readings >= 3`) from `a4i_semantic.fact_heat_cell` joined with `a4i_ml.point_features` and a `geohash-5` (~5 km × 5 km) spatial-block holdout split (`is_eval`: `1,378` train / `484` eval across `22` blocks). | Training and spatial-block evaluation table for `a4i_ml.offset_model_v1`. |
| `a4i_ml.offset_model_v1` | BQML Model (`LINEAR_REG`) | Predicts `offset_f` (°F above/below the `82.06 °F` campaign mean) from physical/built-environment features (`enable_global_explain = TRUE`, `l2_reg = 0.1`); beats predict-zero baseline on held-out spatial blocks (`MAE = 1.254 °F` vs. `1.355 °F`, `-7.5%`). | Powers `ML.EXPLAIN_PREDICT` (`sql/serve/explain_point.sql`) and `ML.GLOBAL_EXPLAIN` for the agent and candidate grid scoring. |
| `a4i_ml.grid_predictions` | Table (`5,618` rows) | ~250 m candidate grid inside `campaign_footprint` (`4,502` unmeasured + `1,116` measured points across `100` tracts) scored with `ML.EXPLAIN_PREDICT` (`predicted_offset_f`, `top_feature_attributions`) and joined with tract vulnerability metrics. | Pre-computed serving table for `sql/serve/rank_sites.sql` to rank and select non-overlapping permanent walkable cooling-center sites. |

