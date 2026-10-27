-- 03_evaluate.sql: is the model better than knowing nothing, and what does it lean on?
-- Owner : data lane. Paste every result into docs/DECISIONS.md; these numbers go in the deck.

-- 1) Model metrics on the spatial-block eval split
SELECT * FROM ML.EVALUATE(MODEL `PROJECT.a4i_ml.offset_model_v1`);

-- 2) The baseline any model must beat: predict 0 (= "every place is average")
SELECT
  ROUND(AVG(ABS(offset_f)), 3)          AS baseline_mae_predict_zero,
  ROUND(SQRT(AVG(offset_f * offset_f)), 3) AS baseline_rmse_predict_zero,
  COUNT(*) AS eval_cells
FROM `PROJECT.a4i_ml.train_cells`
WHERE is_eval;

-- 3) Where is it wrong? Residuals by eval block (spatially clustered error = missing feature)
SELECT
  block_id,
  COUNT(*) AS cells,
  ROUND(AVG(predicted_offset_f - offset_f), 2) AS mean_error,
  ROUND(AVG(ABS(predicted_offset_f - offset_f)), 2) AS mae
FROM ML.PREDICT(MODEL `PROJECT.a4i_ml.offset_model_v1`,
                (SELECT * FROM `PROJECT.a4i_ml.train_cells` WHERE is_eval))
GROUP BY block_id
ORDER BY mae DESC;

-- 4) What the model leans on, globally (the decade track's headline)
SELECT * FROM ML.GLOBAL_EXPLAIN(MODEL `PROJECT.a4i_ml.offset_model_v1`);

-- 5) Coefficients (linear model: direction + magnitude per standardized feature)
SELECT processed_input, ROUND(weight, 3) AS weight
FROM ML.WEIGHTS(MODEL `PROJECT.a4i_ml.offset_model_v1`)
ORDER BY ABS(weight) DESC;

-- Leakage tripwires:
--   r2_score > 0.9 on this split → a feature contains the answer. Find it.
--   mean_absolute_error >= baseline_mae_predict_zero → no signal. Add built-environment data.
