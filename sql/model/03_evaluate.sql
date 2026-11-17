-- a4i_grid.model_evaluation
-- Held-out score of heat_offset_v1 next to the "predict the average everywhere" baseline.
-- The held-out cells are whole ~1 km blocks the model never trained on (188 cells).
-- One holdout is a small sample: cross_validate.sh repeats this over 5 different block
-- splits, and the README reports both.

CREATE OR REPLACE TABLE a4i_grid.model_evaluation AS
WITH
holdout AS (
  SELECT * FROM a4i_grid.cell_model_input WHERE offset_f IS NOT NULL AND holdout
),
train_mean AS (
  SELECT AVG(offset_f) AS m FROM a4i_grid.cell_model_input
  WHERE offset_f IS NOT NULL AND NOT holdout
),
model_eval AS (
  SELECT * FROM ML.EVALUATE(MODEL a4i_grid.heat_offset_v1, (SELECT * FROM holdout))
)
SELECT
  'heat_offset_v1'                        AS model,
  CURRENT_TIMESTAMP()                     AS evaluated_at,
  (SELECT COUNT(*) FROM holdout)          AS holdout_cells,
  e.mean_absolute_error                   AS holdout_mae_f,
  e.r2_score                              AS holdout_r2,
  (SELECT AVG(ABS(h.offset_f - t.m)) FROM holdout h, train_mean t) AS baseline_mae_f,
  1 - e.mean_absolute_error
    / (SELECT AVG(ABS(h.offset_f - t.m)) FROM holdout h, train_mean t) AS mae_reduction_vs_baseline
FROM model_eval e;
