-- 02_train.sql: training cells + offset_model_v1.
-- Purpose : aggregate 1 Hz readings to ~150 m cells, label each with its offset from the
--           campaign mean, assign a spatial-block eval split, train LINEAR_REG.
-- Inputs  : PROJECT.a4i_climate.heat_observations, PROJECT.a4i_ml.point_features
-- Outputs : PROJECT.a4i_ml.train_cells, PROJECT.a4i_ml.offset_model_v1
-- Owner   : data lane

CREATE OR REPLACE TABLE `PROJECT.a4i_ml.train_cells` AS
WITH obs AS (
  SELECT ST_GEOGPOINT(longitude, latitude) AS g, latitude, longitude, temp_f
  FROM `PROJECT.a4i_climate.heat_observations`
),
mu AS (SELECT AVG(temp_f) AS m FROM obs),
cells AS (
  SELECT
    ST_GEOHASH(g, 7)              AS cell_id,       -- ≈153 m × 153 m
    ST_GEOHASH(g, 5)              AS block_id,      -- ≈4.9 km × 4.9 km (split unit)
    AVG(latitude)                 AS lat,
    AVG(longitude)                AS lon,
    AVG(temp_f) - (SELECT m FROM mu) AS offset_f,
    COUNT(*)                      AS n_readings
  FROM obs
  GROUP BY cell_id, block_id
  HAVING n_readings >= 3                            -- drop single-blip cells
),
feats AS (
  SELECT * FROM `PROJECT.a4i_ml.point_features`(
    (SELECT ARRAY_AGG(STRUCT(cell_id AS point_id, lat, lon)) FROM cells))
)
SELECT
  c.cell_id, c.block_id, c.n_readings, c.offset_f,
  -- spatial-block split: whole ~5 km blocks go to eval, so eval cells have no next-door twin in train
  MOD(ABS(FARM_FINGERPRINT(c.block_id)), 5) = 0 AS is_eval,
  f.* EXCEPT (point_id, lat, lon, in_footprint, meters_to_tract_point, geo_id),
  f.geo_id
FROM cells c
JOIN feats f ON f.point_id = c.cell_id;

-- Check the split isn't degenerate (want ~15–25% eval, both sides with spread):
-- SELECT is_eval, COUNT(*) n, ROUND(AVG(offset_f),2) mean, ROUND(STDDEV(offset_f),2) sd
-- FROM `PROJECT.a4i_ml.train_cells` GROUP BY is_eval;

CREATE OR REPLACE MODEL `PROJECT.a4i_ml.offset_model_v1`
OPTIONS (
  model_type          = 'LINEAR_REG',
  input_label_cols    = ['offset_f'],
  data_split_method   = 'CUSTOM',
  data_split_col      = 'is_eval',          -- TRUE rows are held out for evaluation
  l2_reg              = 0.1,
  enable_global_explain = TRUE,
  labels = [('app', 'heat-planner'), ('lane', 'data')]
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
FROM `PROJECT.a4i_ml.train_cells`;
-- BQML standardizes numeric features and imputes NULLs with the training mean automatically.
