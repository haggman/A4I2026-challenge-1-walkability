-- sql/ml/04_serve.sql: online ML.EXPLAIN_PREDICT query + batch ~250 m candidate grid (`a4i_ml.grid_predictions`).
-- Owner : data / ml lane (DS 1 & DS 2)

-- (a) ONLINE: explain one arbitrary point (@lat FLOAT64, @lon FLOAT64)
-- Also saved to `sql/serve/explain_point.sql` for the agent tool.
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

-- (b) BATCH: candidate grid (~250 m) inside the Atlanta campaign footprint (5,618 points: 4,502 unmeasured, 1,116 measured)
CREATE OR REPLACE TABLE `qwiklabs-gcp-04-ec3596addc43.a4i_ml.grid_predictions`
OPTIONS (
  description = 'Batch ~250 m candidate grid inside the Atlanta campaign footprint scored with ML.EXPLAIN_PREDICT(offset_model_v1) and joined with tract vulnerability context.',
  labels = [('app', 'heat-planner'), ('lane', 'data'), ('layer', 'ml')]
) AS
WITH bbox AS (
  SELECT MIN(latitude) lat0, MAX(latitude) lat1, MIN(longitude) lon0, MAX(longitude) lon1
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.heat_readings`
  WHERE NOT is_temp_outlier
),
grid AS (
  SELECT FORMAT('g_%.4f_%.4f', lat, lon) AS point_id, lat, lon
  FROM bbox,
       UNNEST(GENERATE_ARRAY(lat0, lat1, 0.00225)) AS lat,
       UNNEST(GENERATE_ARRAY(lon0, lon1, 0.00225 / COS(ACOS(-1) * (lat0 + lat1) / 360))) AS lon
),
inside AS (
  SELECT g.* FROM grid g, `qwiklabs-gcp-04-ec3596addc43.a4i_ml.campaign_footprint` f
  WHERE ST_COVERS(f.footprint, ST_GEOGPOINT(g.lon, g.lat))
),
pred AS (
  SELECT * FROM ML.EXPLAIN_PREDICT(
    MODEL `qwiklabs-gcp-04-ec3596addc43.a4i_ml.offset_model_v1`,
    (SELECT * FROM `qwiklabs-gcp-04-ec3596addc43.a4i_ml.point_features`(
       (SELECT ARRAY_AGG(STRUCT(point_id, lat, lon)) FROM inside))),
    STRUCT(5 AS top_k_features))
),
measured AS (
  SELECT DISTINCT i.point_id
  FROM inside i
  JOIN `qwiklabs-gcp-04-ec3596addc43.a4i_core.heat_readings` o
    ON ST_DWITHIN(ST_GEOGPOINT(o.longitude, o.latitude), ST_GEOGPOINT(i.lon, i.lat), 150)
  WHERE NOT o.is_temp_outlier
)
SELECT
  p.point_id, p.lat, p.lon, p.geo_id,
  ROUND(p.predicted_offset_f, 2) AS predicted_offset_f,
  p.top_feature_attributions     AS drivers,
  t.total_pop, t.pop_65_plus, t.share_65_plus, t.car_free_households,
  t.median_age, t.poverty_rate, t.no_vehicle_rate, t.median_income,
  m.point_id IS NULL AS unmeasured,
  'offset_model_v1' AS model_version,
  CURRENT_TIMESTAMP() AS scored_at
FROM pred p
LEFT JOIN `qwiklabs-gcp-04-ec3596addc43.a4i_ml.tracts_enriched` t USING (geo_id)
LEFT JOIN measured m ON m.point_id = p.point_id
WHERE p.geo_id IS NOT NULL;
