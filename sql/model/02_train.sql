-- a4i_grid.heat_offset_v1
-- Predicts a cell's heat offset: degrees F above (+) or below (-) the campaign mean on
-- the measured afternoon. NOT a temperature. Temperature for a day =
--   that day's city high (forecast or station) + predicted offset.
--
-- LINEAR_REG: free-tier, trains in seconds, and ML.EXPLAIN_PREDICT gives exact per-feature
-- attributions. Trained on driven cells outside the held-out blocks only.

CREATE OR REPLACE MODEL a4i_grid.heat_offset_v1
OPTIONS (
  model_type            = 'LINEAR_REG',
  input_label_cols      = ['offset_f'],
  data_split_method     = 'NO_SPLIT',     -- we hold out whole blocks ourselves
  enable_global_explain = TRUE
) AS
SELECT
  nbr_offset_1km,
  tract_water_share,
  dist_open_space_m,
  bg_housing_units_per_km2,
  trees_100m,
  tree_dbh_sum_100m,
  offset_f
FROM a4i_grid.cell_model_input
WHERE offset_f IS NOT NULL
  AND NOT holdout;
