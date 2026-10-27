-- sql/serve/explain_point.sql: Online ML.EXPLAIN_PREDICT serving query for the ADK agent.
-- Params: @lat FLOAT64, @lon FLOAT64
SELECT
  e.point_id,
  e.lat,
  e.lon,
  e.geo_id,
  e.in_footprint,
  ROUND(e.predicted_offset_f, 2)        AS predicted_offset_f,
  ROUND(e.baseline_prediction_value, 2) AS baseline_offset_f,
  ARRAY(
    SELECT AS STRUCT a.feature, ROUND(a.attribution, 2) AS attribution_f
    FROM UNNEST(e.top_feature_attributions) a
    ORDER BY ABS(a.attribution) DESC
  ) AS drivers,
  ROUND(e.approximation_error, 3)       AS approximation_error
FROM ML.EXPLAIN_PREDICT(
  MODEL `qwiklabs-gcp-04-ec3596addc43.a4i_ml.offset_model_v1`,
  (SELECT * FROM `qwiklabs-gcp-04-ec3596addc43.a4i_ml.point_features`([STRUCT('query' AS point_id, @lat AS lat, @lon AS lon)])),
  STRUCT(5 AS top_k_features)
) e;
