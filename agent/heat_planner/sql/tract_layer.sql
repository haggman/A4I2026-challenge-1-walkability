WITH preds AS (
  SELECT geo_id, ROUND(AVG(predicted_offset_f), 2) AS predicted_offset_f
  FROM `PROJECT.a4i_ml.grid_predictions`
  GROUP BY geo_id
),
shapes AS (
  SELECT
    LPAD(TRIM(CAST(geo_id AS STRING)), 11, '0') AS geo_id,
    ST_SIMPLIFY(tract_geom, LEAST(GREATEST(@simplify_m, 5.0), 100.0)) AS geom
  FROM `bigquery-public-data.geo_census_tracts.us_census_tracts_national`
)
SELECT
  d.geo_id,
  p.predicted_offset_f,
  ROUND(d.no_vehicle_rate, 4) AS no_vehicle_rate,
  ROUND(d.share_65_plus, 4) AS share_65_plus,
  ROUND(d.poverty_rate, 4) AS poverty_rate,
  d.population,
  ST_ASGEOJSON(s.geom) AS geometry_json
FROM `PROJECT.a4i_semantic.dim_tract` d
JOIN shapes s USING (geo_id)
LEFT JOIN preds p USING (geo_id)
ORDER BY d.geo_id
