-- nearest_tract.sql: assign any point(s) to the nearest census-tract internal point.
-- Purpose : the one spatial join every lane needs (features, demographics, audit).
-- Note    : tract_demographics carries internal points, not polygons. Nearest-centroid is a
--           documented approximation; say so. For exact containment, join
--           bigquery-public-data.geo_census_tracts.<national table>.tract_geom with ST_CONTAINS.
-- Params  : @lat FLOAT64, @lon FLOAT64   (single point form)

SELECT
  t.geo_id,
  ROUND(ST_DISTANCE(ST_GEOGPOINT(@lon, @lat), ST_GEOGPOINT(t.tract_lon, t.tract_lat))) AS meters_to_tract_point,
  t.total_pop, t.median_age, t.median_income, t.poverty_rate, t.no_vehicle_rate,
  t.median_year_structure_built, t.households
FROM `PROJECT.a4i_climate.tract_demographics` t
ORDER BY ST_DISTANCE(ST_GEOGPOINT(@lon, @lat), ST_GEOGPOINT(t.tract_lon, t.tract_lat))
LIMIT 1;

-- Batch form (many points → nearest tract): see the `nearest` CTE in
-- .agents/skills/bqml-offset-model/resources/01_features.sql (ARRAY_AGG ... ORDER BY ST_DISTANCE LIMIT 1,
-- pre-filtered with ST_DWITHIN 5000 m so it never does a full cross join).
