-- sql/ml/03_evaluate.sql: evaluate `a4i_ml.offset_model_v1` against the predict-zero baseline on held-out geohash-5 spatial blocks.
-- Owner : data / ml lane (DS 1)

-- 1) Model metrics on the held-out spatial-block eval split (484 cells across 6 geohash-5 blocks)
SELECT
  ROUND(mean_absolute_error, 3) AS eval_mae,
  ROUND(SQRT(mean_squared_error), 3) AS eval_rmse,
  ROUND(r2_score, 3) AS eval_r2,
  ROUND(explained_variance, 3) AS eval_explained_var
FROM ML.EVALUATE(
  MODEL `qwiklabs-gcp-04-ec3596addc43.a4i_ml.offset_model_v1`,
  (SELECT * FROM `qwiklabs-gcp-04-ec3596addc43.a4i_ml.train_cells` WHERE is_eval)
);

-- 2) Predict-zero baseline on the same held-out spatial-block eval split
SELECT
  ROUND(AVG(ABS(offset_f)), 3) AS baseline_mae_predict_zero,
  ROUND(SQRT(AVG(offset_f * offset_f)), 3) AS baseline_rmse_predict_zero,
  COUNT(*) AS eval_cells
FROM `qwiklabs-gcp-04-ec3596addc43.a4i_ml.train_cells`
WHERE is_eval;

-- 3) Global feature importance (ML.GLOBAL_EXPLAIN)
SELECT
  feature,
  ROUND(attribution, 4) AS global_attribution
FROM ML.GLOBAL_EXPLAIN(MODEL `qwiklabs-gcp-04-ec3596addc43.a4i_ml.offset_model_v1`)
ORDER BY attribution DESC;

-- 4) Model weights (ML.WEIGHTS)
SELECT
  processed_input,
  ROUND(weight, 4) AS weight
FROM ML.WEIGHTS(MODEL `qwiklabs-gcp-04-ec3596addc43.a4i_ml.offset_model_v1`)
ORDER BY ABS(weight) DESC;
