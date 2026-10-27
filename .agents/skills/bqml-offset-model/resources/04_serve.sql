-- 04_serve.sql: the two ways the agent consumes the model.
-- Owner : data lane writes it; agent lane wraps it. Copy (a) to sql/serve/explain_point.sql.

-- (a) ONLINE: explain one arbitrary point. This is the agent tool's query.
--     Params: @lat FLOAT64, @lon FLOAT64. Cost: tiny. Latency: ~1–3 s.
SELECT
  e.point_id,
  e.lat, e.lon, e.geo_id, e.in_footprint,
  ROUND(e.predicted_offset_f, 2)        AS predicted_offset_f,
  ROUND(e.baseline_prediction_value, 2) AS baseline_offset_f,
  ARRAY(SELECT AS STRUCT a.feature, ROUND(a.attribution, 2) AS attribution_f
        FROM UNNEST(e.top_feature_attributions) a
        ORDER BY ABS(a.attribution) DESC) AS drivers,
  ROUND(e.approximation_error, 3)       AS approximation_error
FROM ML.EXPLAIN_PREDICT(
  MODEL `PROJECT.a4i_ml.offset_model_v1`,
  (SELECT * FROM `PROJECT.a4i_ml.point_features`([STRUCT('query' AS point_id, @lat AS lat, @lon AS lon)])),
  STRUCT(5 AS top_k_features)) e;
-- The tool must check in_footprint and a non-NULL geo_id; if either fails → status "out_of_scope".

-- (b) BATCH: candidate grid (~250 m) inside the footprint, predicted + explained once.
--     The ranking tool reads this table. It's fast, cheap and demo-safe. Rebuild after promoting a model.
CREATE OR REPLACE TABLE `PROJECT.a4i_ml.grid_predictions`
OPTIONS (labels = [('app', 'heat-planner')]) AS
WITH bbox AS (
  SELECT MIN(latitude) lat0, MAX(latitude) lat1, MIN(longitude) lon0, MAX(longitude) lon1
  FROM `PROJECT.a4i_climate.heat_observations`
),
grid AS (
  SELECT FORMAT('g_%.4f_%.4f', lat, lon) AS point_id, lat, lon
  FROM bbox,
       UNNEST(GENERATE_ARRAY(lat0, lat1, 0.00225)) AS lat,                 -- ≈250 m
       UNNEST(GENERATE_ARRAY(lon0, lon1, 0.00225 / COS(ACOS(-1) * (lat0 + lat1) / 360))) AS lon
),
inside AS (
  SELECT g.* FROM grid g, `PROJECT.a4i_ml.campaign_footprint` f
  WHERE ST_COVERS(f.footprint, ST_GEOGPOINT(g.lon, g.lat))
),
pred AS (
  SELECT * FROM ML.EXPLAIN_PREDICT(
    MODEL `PROJECT.a4i_ml.offset_model_v1`,
    (SELECT * FROM `PROJECT.a4i_ml.point_features`(
       (SELECT ARRAY_AGG(STRUCT(point_id, lat, lon)) FROM inside))),
    STRUCT(5 AS top_k_features))
),
measured AS (   -- grid points with a Heat Watch reading within 150 m
  SELECT DISTINCT i.point_id
  FROM inside i
  JOIN `PROJECT.a4i_climate.heat_observations` o
    ON ST_DWITHIN(ST_GEOGPOINT(o.longitude, o.latitude), ST_GEOGPOINT(i.lon, i.lat), 150)
)
SELECT
  p.point_id, p.lat, p.lon, p.geo_id,
  ROUND(p.predicted_offset_f, 2) AS predicted_offset_f,
  p.top_feature_attributions     AS drivers,
  -- vulnerability context for ranking (NOT model inputs)
  t.total_pop, t.median_age, t.poverty_rate, t.no_vehicle_rate, t.median_income,
  -- a true "unmeasured" point: no Heat Watch reading within 150 m. The demo should show one.
  m.point_id IS NULL AS unmeasured,
  'offset_model_v1' AS model_version,
  CURRENT_TIMESTAMP() AS scored_at
FROM pred p
LEFT JOIN `PROJECT.a4i_ml.tracts_enriched` t USING (geo_id)
LEFT JOIN measured m ON m.point_id = p.point_id
WHERE p.geo_id IS NOT NULL;
