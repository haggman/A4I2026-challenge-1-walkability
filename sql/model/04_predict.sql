-- a4i_grid.cell_heat_predicted
-- Every land cell: predicted offset with per-feature attributions (ML.EXPLAIN_PREDICT),
-- next to the measured offset where one exists.
--
--   predicted_offset_f   model output for every land cell (driven cells too, for comparison)
--   offset_best_f        measured offset if the cell was driven, else the prediction.
--                        Use this for maps, rankings and history.
--   attributions         [{feature, attribution_f}], each feature's contribution in degrees F
--                        relative to the model's baseline (an average cell); they sum to
--                        predicted_offset_f - baseline_offset_f.
--   confidence           'measured'  -- driven cell
--                        'near_data' -- within 1 km of measured streets (nbr_n > 0)
--                        'extrapolated' -- nothing measured within 1 km: built features only,
--                                       which on their own barely beat the city average.

CREATE OR REPLACE TABLE a4i_grid.cell_heat_predicted
CLUSTER BY cell_i, cell_j AS
SELECT
  p.cell_i,
  p.cell_j,
  p.predicted_offset_f,
  p.offset_f                                          AS measured_offset_f,
  IFNULL(p.offset_f, p.predicted_offset_f)            AS offset_best_f,
  p.baseline_prediction_value                         AS baseline_offset_f,
  ARRAY(
    SELECT AS STRUCT a.feature, a.attribution AS attribution_f
    FROM UNNEST(p.top_feature_attributions) a
    ORDER BY ABS(a.attribution) DESC
  )                                                   AS attributions,
  p.nbr_n,
  CASE
    WHEN p.offset_f IS NOT NULL THEN 'measured'
    WHEN p.nbr_n > 0            THEN 'near_data'
    ELSE 'extrapolated'
  END                                                 AS confidence
FROM ML.EXPLAIN_PREDICT(
  MODEL a4i_grid.heat_offset_v1,
  (SELECT * FROM a4i_grid.cell_model_input),
  STRUCT(10 AS top_k_features)
) AS p;
