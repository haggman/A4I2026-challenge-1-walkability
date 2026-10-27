SELECT
  e.point_id,
  e.lat,
  e.lon,
  e.geo_id,
  e.in_footprint,
  ROUND(e.predicted_offset_f, 2)        AS predicted_offset_f,
  ROUND(e.baseline_prediction_value, 2) AS baseline_offset_f,
  ROUND(fp.campaign_mean_f, 3)          AS campaign_mean_f,
  TO_JSON_STRING(ARRAY(
    SELECT AS STRUCT a.feature, ROUND(a.attribution, 2) AS attribution_f
    FROM UNNEST(e.top_feature_attributions) a
    ORDER BY ABS(a.attribution) DESC
  )) AS drivers_json,
  ROUND(e.approximation_error, 3)       AS approximation_error
FROM ML.EXPLAIN_PREDICT(
  MODEL `PROJECT.a4i_ml.MODEL_ID`,
  (SELECT * FROM `PROJECT.a4i_ml.point_features`([STRUCT('query' AS point_id, @lat AS lat, @lon AS lon)])),
  STRUCT(5 AS top_k_features)
) e
CROSS JOIN `PROJECT.a4i_ml.campaign_footprint` fp
LIMIT 1
