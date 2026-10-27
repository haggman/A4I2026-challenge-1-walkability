-- sql/semantic/06_tvf_vulnerable_population.sql
-- Purpose : Table-valued function returning total population, 65+ residents, and car-free households within
--           `radius_m` meters of `(lat, lon)` using straight-line distance to census tract internal points.
-- Inputs  : Parameters `lat FLOAT64, lon FLOAT64, radius_m FLOAT64`; reads `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`
-- Outputs : Table Function `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.vulnerable_population(lat FLOAT64, lon FLOAT64, radius_m FLOAT64)`
-- Owner   : data lane
-- Why     : Feeds cooling-center coverage ranking by estimating how many car-free households and 65+ seniors
--           live within walking/service radius of a candidate site. Documented approximation: sums tracts whose
--           internal-point centroid lies within `radius_m` straight-line meters of `(lat, lon)`.
--
-- Example query:
--   SELECT * FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.vulnerable_population`(33.7537, -84.3863, 1500);

CREATE OR REPLACE TABLE FUNCTION `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.vulnerable_population`(
  lat FLOAT64,
  lon FLOAT64,
  radius_m FLOAT64
)
OPTIONS (
  description = 'Estimates vulnerable population within radius_m straight-line meters of (lat, lon) by summing census tracts whose internal-point centroid falls within radius_m: car-free households, 65+ seniors, total population, and population-weighted poverty/no-vehicle rates.'
) AS (
  WITH matched AS (
    SELECT
      geo_id,
      total_pop,
      pop_65_plus,
      no_cars AS car_free_households,
      households,
      poverty_rate,
      no_vehicle_rate,
      ST_DISTANCE(ST_GEOGPOINT(lon, lat), tract_centroid_geog) AS dist_m
    FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`
    WHERE ST_DWITHIN(ST_GEOGPOINT(lon, lat), tract_centroid_geog, radius_m)
  )
  SELECT
    lat AS query_lat,
    lon AS query_lon,
    radius_m,
    COUNT(*) AS tracts_within_radius,
    COALESCE(ROUND(SUM(total_pop), 0), 0) AS population_within_radius,
    COALESCE(ROUND(SUM(pop_65_plus), 0), 0) AS pop_65_plus_within_radius,
    COALESCE(ROUND(SUM(car_free_households), 0), 0) AS car_free_households_within_radius,
    COALESCE(ROUND(SUM(households), 0), 0) AS households_within_radius,
    ROUND(SAFE_DIVIDE(SUM(pop_65_plus), NULLIF(SUM(total_pop), 0)), 4) AS share_65_plus_within_radius,
    ROUND(SAFE_DIVIDE(SUM(car_free_households), NULLIF(SUM(households), 0)), 4) AS no_vehicle_rate_within_radius,
    ROUND(SAFE_DIVIDE(SUM(total_pop * poverty_rate), NULLIF(SUM(IF(poverty_rate IS NULL, 0, total_pop)), 0)), 4) AS pop_weighted_poverty_rate,
    ARRAY_AGG(geo_id ORDER BY dist_m) AS tract_geo_ids
  FROM matched
);
