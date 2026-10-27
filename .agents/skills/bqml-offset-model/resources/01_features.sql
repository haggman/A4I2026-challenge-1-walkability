-- 01_features.sql: shared feature layer for train AND serve.
-- Purpose : one feature definition (table function point_features) so the model sees identical
--           features at training time and when the agent asks about an arbitrary point.
-- Inputs  : PROJECT.a4i_climate.{tract_demographics, heat_observations},
--           bigquery-public-data.geo_census_tracts.us_census_tracts_national (verify the name with
--           INFORMATION_SCHEMA.TABLES; the notebook discovers it dynamically)
-- Outputs : PROJECT.a4i_ml.tracts_enriched, PROJECT.a4i_ml.campaign_footprint,
--           TABLE FUNCTION PROJECT.a4i_ml.point_features(pts)
-- Owner   : data lane
-- NOTE    : no race/ethnicity, no temp/heat-index/humidity columns. Ever.

-- 1) Tracts with land area → densities ---------------------------------------
CREATE OR REPLACE TABLE `PROJECT.a4i_ml.tracts_enriched` AS
SELECT
  d.geo_id,
  d.tract_lat,
  d.tract_lon,
  d.total_pop,
  d.housing_units,
  d.households,
  -- ACS sometimes encodes "1939 or earlier"/unknown oddly; clamp to a plausible range
  IF(d.median_year_structure_built BETWEEN 1900 AND 2025, d.median_year_structure_built, NULL)
    AS median_year_built,
  SAFE_DIVIDE(d.total_pop,     SAFE_CAST(g.area_land_meters AS FLOAT64) / 1e6) AS pop_density_km2,
  SAFE_DIVIDE(d.housing_units, SAFE_CAST(g.area_land_meters AS FLOAT64) / 1e6) AS housing_density_km2,
  SAFE_CAST(g.area_water_meters AS FLOAT64)
    / NULLIF(SAFE_CAST(g.area_land_meters AS FLOAT64) + SAFE_CAST(g.area_water_meters AS FLOAT64), 0)
    AS water_share,
  -- vulnerability columns are carried for RANKING and AUDIT, not for the model
  d.median_age, d.median_income, d.poverty_rate, d.no_vehicle_rate
FROM `PROJECT.a4i_climate.tract_demographics` d
LEFT JOIN `bigquery-public-data.geo_census_tracts.us_census_tracts_national` g
  ON g.geo_id = d.geo_id;           -- d.geo_id is already LPAD-ed to 11 by the loader

-- Check: two numbers, not one.
-- SELECT COUNT(*) n, COUNTIF(pop_density_km2 IS NULL) no_area FROM `PROJECT.a4i_ml.tracts_enriched`;

-- 2) Where the model is allowed to speak --------------------------------------
CREATE OR REPLACE TABLE `PROJECT.a4i_ml.campaign_footprint` AS
SELECT
  ST_BUFFER(ST_CONVEXHULL(ST_UNION_AGG(ST_GEOGPOINT(longitude, latitude))), 1000) AS footprint,
  ST_GEOGPOINT(AVG(longitude), AVG(latitude)) AS center,
  AVG(temp_f) AS campaign_mean_f
FROM `PROJECT.a4i_climate.heat_observations`;

-- 3) The feature function ------------------------------------------------------
CREATE OR REPLACE TABLE FUNCTION `PROJECT.a4i_ml.point_features`(
  pts ARRAY<STRUCT<point_id STRING, lat FLOAT64, lon FLOAT64>>)
AS (
  WITH p AS (
    SELECT point_id, lat, lon, ST_GEOGPOINT(lon, lat) AS g FROM UNNEST(pts)
  ),
  tr AS (
    SELECT *, ST_GEOGPOINT(tract_lon, tract_lat) AS tg FROM `PROJECT.a4i_ml.tracts_enriched`
  ),
  nearest AS (
    SELECT
      p.point_id,
      ARRAY_AGG(STRUCT(tr.geo_id, tr.median_year_built, tr.pop_density_km2,
                       tr.housing_density_km2, tr.water_share,
                       ST_DISTANCE(p.g, tr.tg) AS meters)
                ORDER BY ST_DISTANCE(p.g, tr.tg) LIMIT 1)[OFFSET(0)] AS nt
    FROM p JOIN tr ON ST_DWITHIN(p.g, tr.tg, 5000)
    GROUP BY p.point_id
  ),
  ring AS (   -- neighbourhood context: what surrounds the point, not just its tract
    SELECT
      p.point_id,
      SUM(tr.total_pop)     AS pop_within_1500m,
      SUM(tr.housing_units) AS housing_within_1500m,
      AVG(tr.median_year_built) AS mean_year_built_1500m
    FROM p JOIN tr ON ST_DWITHIN(p.g, tr.tg, 1500)
    GROUP BY p.point_id
  )
  SELECT
    p.point_id,
    p.lat,
    p.lon,
    n.nt.geo_id                                   AS geo_id,
    ST_COVERS(f.footprint, p.g)                   AS in_footprint,
    n.nt.meters                                   AS meters_to_tract_point,
    -- model features (physical / built environment only) --------------------
    ST_DISTANCE(p.g, f.center) / 1000             AS km_from_center,
    n.nt.median_year_built                        AS median_year_built,
    n.nt.pop_density_km2                          AS pop_density_km2,
    n.nt.housing_density_km2                      AS housing_density_km2,
    COALESCE(n.nt.water_share, 0)                 AS water_share,
    COALESCE(r.pop_within_1500m, 0)               AS pop_within_1500m,
    COALESCE(r.housing_within_1500m, 0)           AS housing_within_1500m,
    r.mean_year_built_1500m                       AS mean_year_built_1500m
  FROM p
  CROSS JOIN `PROJECT.a4i_ml.campaign_footprint` f
  LEFT JOIN nearest n USING (point_id)
  LEFT JOIN ring    r USING (point_id)
);
