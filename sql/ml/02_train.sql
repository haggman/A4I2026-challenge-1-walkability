-- sql/ml/02_train.sql: training cells + offset_model_v1.
-- Purpose : Read aggregated ~150 m (geohash-7) cells from `a4i_semantic.fact_heat_cell` (n_readings >= 3),
--           join physical built-environment features from `a4i_ml.point_features`, assign a balanced
--           geohash-5 (~5 km x 5 km) spatial-block eval split, and train `a4i_ml.offset_model_v1`.
-- Inputs  : `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_heat_cell`,
--           `qwiklabs-gcp-04-ec3596addc43.a4i_ml.point_features`
-- Outputs : `qwiklabs-gcp-04-ec3596addc43.a4i_ml.train_cells`,
--           `qwiklabs-gcp-04-ec3596addc43.a4i_ml.offset_model_v1`
-- Owner   : data / ml lane (DS 1)

CREATE OR REPLACE TABLE `qwiklabs-gcp-04-ec3596addc43.a4i_ml.train_cells`
OPTIONS (
  description = 'Training and spatial-block evaluation cells (geohash-7, >=3 readings) built from a4i_semantic.fact_heat_cell and a4i_ml.point_features.',
  labels = [('app', 'heat-planner'), ('lane', 'data'), ('layer', 'ml')]
) AS
WITH cells AS (
  SELECT
    cell_id,
    block_id,
    lat,
    lon,
    offset_f,
    n_readings
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_heat_cell`
  WHERE n_readings >= 3
),
feats AS (
  SELECT *
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_ml.point_features`(
    (SELECT ARRAY_AGG(STRUCT(cell_id AS point_id, lat, lon)) FROM cells)
  )
)
SELECT
  c.cell_id,
  c.block_id,
  c.n_readings,
  c.offset_f,
  -- Spatial-block split: whole ~5 km (geohash-5) blocks go to eval (fold 3 = 484 cells across 6 blocks, 26.0% holdout)
  MOD(ABS(FARM_FINGERPRINT(c.block_id)), 5) = 3 AS is_eval,
  f.* EXCEPT (point_id, lat, lon, in_footprint, meters_to_tract_point, geo_id),
  f.geo_id
FROM cells c
JOIN feats f
  ON f.point_id = c.cell_id;

CREATE OR REPLACE MODEL `qwiklabs-gcp-04-ec3596addc43.a4i_ml.offset_model_v1`
OPTIONS (
  model_type            = 'LINEAR_REG',
  input_label_cols      = ['offset_f'],
  data_split_method     = 'CUSTOM',
  data_split_col        = 'is_eval',
  l2_reg                = 0.1,
  enable_global_explain = TRUE
) AS
SELECT
  offset_f,
  is_eval,
  km_from_center,
  median_year_built,
  pop_density_km2,
  housing_density_km2,
  water_share,
  pop_within_1500m,
  housing_within_1500m,
  mean_year_built_1500m
FROM `qwiklabs-gcp-04-ec3596addc43.a4i_ml.train_cells`;
