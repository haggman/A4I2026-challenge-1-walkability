-- sql/ml/01_features.sql
-- Purpose : Shared feature layer for training AND serving, adapted from skills/bqml-offset-model/resources/01_features.sql
--           to read from cleaned `a4i_core` and `a4i_semantic` instead of raw `a4i_climate`.
-- Inputs  : `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`,
--           `qwiklabs-gcp-04-ec3596addc43.a4i_core.heat_readings`,
--           `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.dim_tract`
-- Outputs : `qwiklabs-gcp-04-ec3596addc43.a4i_ml.tracts_enriched`,
--           `qwiklabs-gcp-04-ec3596addc43.a4i_ml.campaign_footprint`,
--           TABLE FUNCTION `qwiklabs-gcp-04-ec3596addc43.a4i_ml.point_features(pts)`
-- Owner   : data lane
-- Why     : Eliminates train/serve skew by computing identical physical/built-environment features for
--           training cells, the 250 m candidate grid, and live ML.EXPLAIN_PREDICT queries, while sourcing
--           sentinel-cleaned, ACS-65+-enriched tracts from `a4i_core.tracts` and non-outlier readings from
--           `a4i_core.heat_readings`. Contains zero race/ethnicity columns and zero drive-day measurements
--           (temp_f, heat_index_f, humidity_pct, observed_at) in model features.

-- 1) Sentinel-free, enriched tracts for feature extraction, ranking, and post-hoc audit
CREATE OR REPLACE TABLE `qwiklabs-gcp-04-ec3596addc43.a4i_ml.tracts_enriched`
OPTIONS (
  description = 'Sentinel-cleaned Atlanta census tracts (353 tracts) sourced from a4i_core.tracts and a4i_semantic.dim_tract. Supplies physical built-environment densities to point_features() and vulnerability context (65+, car-free households, poverty, income) to ranking and audit.',
  labels = [('app', 'heat-planner'), ('lane', 'data'), ('layer', 'ml')]
) AS
SELECT
  t.geo_id,
  t.tract_lat,
  t.tract_lon,
  t.total_pop,
  t.pop_65_plus,
  t.share_65_plus,
  t.housing_units,
  t.households,
  t.no_cars AS car_free_households,
  d.median_year_built,
  t.pop_density_km2,
  t.housing_density_km2,
  t.water_share,
  -- Vulnerability columns carried for post-prediction RANKING and EQUITY AUDIT only (never model inputs)
  t.median_age,
  t.median_income,
  t.poverty_rate,
  t.no_vehicle_rate
FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts` t
JOIN `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.dim_tract` d
  USING (geo_id);

ALTER TABLE `qwiklabs-gcp-04-ec3596addc43.a4i_ml.tracts_enriched`
  ALTER COLUMN geo_id SET OPTIONS (description = '11-character FIPS census tract identifier (string).'),
  ALTER COLUMN tract_lat SET OPTIONS (description = 'Tract internal-point latitude (degrees North, WGS84).'),
  ALTER COLUMN tract_lon SET OPTIONS (description = 'Tract internal-point longitude (degrees East, WGS84).'),
  ALTER COLUMN total_pop SET OPTIONS (description = 'Total resident population in tract (persons).'),
  ALTER COLUMN pop_65_plus SET OPTIONS (description = 'Residents aged 65 years and older (persons, ACS 2020 5-yr).'),
  ALTER COLUMN share_65_plus SET OPTIONS (description = 'Share of tract population aged 65+ (share 0-1).'),
  ALTER COLUMN housing_units SET OPTIONS (description = 'Total housing units in tract (units).'),
  ALTER COLUMN households SET OPTIONS (description = 'Occupied households in tract (households).'),
  ALTER COLUMN car_free_households SET OPTIONS (description = 'Occupied households with zero vehicles available (households).'),
  ALTER COLUMN median_year_built SET OPTIONS (description = 'Median year residential structures were built (calendar year 1900-2025, sentinel-cleaned).'),
  ALTER COLUMN pop_density_km2 SET OPTIONS (description = 'Population density per square kilometer of land (persons per km2).'),
  ALTER COLUMN housing_density_km2 SET OPTIONS (description = 'Housing unit density per square kilometer of land (housing units per km2).'),
  ALTER COLUMN water_share SET OPTIONS (description = 'Share of total tract area covered by water (share 0-1).'),
  ALTER COLUMN median_age SET OPTIONS (description = 'Median resident age (years, sentinel-cleaned; ranking/audit only).'),
  ALTER COLUMN median_income SET OPTIONS (description = 'Median household income in USD (sentinel-cleaned; ranking/audit only).'),
  ALTER COLUMN poverty_rate SET OPTIONS (description = 'Share of population below federal poverty level (share 0-1; ranking/audit only).'),
  ALTER COLUMN no_vehicle_rate SET OPTIONS (description = 'Share of occupied households with no vehicle (share 0-1; ranking/audit only).');

-- 2) Campaign footprint polygon, centroid, and baseline campaign mean from cleaned core readings
CREATE OR REPLACE TABLE `qwiklabs-gcp-04-ec3596addc43.a4i_ml.campaign_footprint`
OPTIONS (
  description = '1 km buffered convex-hull polygon of cleaned Atlanta Heat Watch traverse readings (from a4i_core.heat_readings WHERE NOT is_temp_outlier), traverse centroid, and campaign mean temperature (deg F). Defines where the model is allowed to predict.',
  labels = [('app', 'heat-planner'), ('lane', 'data'), ('layer', 'ml')]
) AS
SELECT
  ST_BUFFER(ST_CONVEXHULL(ST_UNION_AGG(geog)), 1000) AS footprint,
  ST_GEOGPOINT(AVG(longitude), AVG(latitude)) AS center,
  AVG(temp_f) AS campaign_mean_f
FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.heat_readings`
WHERE NOT is_temp_outlier;

ALTER TABLE `qwiklabs-gcp-04-ec3596addc43.a4i_ml.campaign_footprint`
  ALTER COLUMN footprint SET OPTIONS (description = '1,000 m buffered convex hull of non-outlier Atlanta Heat Watch traverse points (GEOGRAPHY).'),
  ALTER COLUMN center SET OPTIONS (description = 'Centroid of non-outlier Atlanta Heat Watch traverse readings (GEOGRAPHY).'),
  ALTER COLUMN campaign_mean_f SET OPTIONS (description = 'Campaign-wide mean temperature across non-outlier traverse readings (deg F; reference baseline for offset_f).');

-- 3) Shared physical/built-environment feature table function for training and serving
CREATE OR REPLACE TABLE FUNCTION `qwiklabs-gcp-04-ec3596addc43.a4i_ml.point_features`(
  pts ARRAY<STRUCT<point_id STRING, lat FLOAT64, lon FLOAT64>>
)
OPTIONS (
  description = 'Shared train/serve feature function mapping arbitrary (point_id, lat, lon) points to physical/built-environment features from a4i_ml.tracts_enriched and a4i_ml.campaign_footprint. Excludes race/ethnicity and drive-day measurements.'
) AS (
  WITH p AS (
    SELECT point_id, lat, lon, ST_GEOGPOINT(lon, lat) AS g
    FROM UNNEST(pts)
  ),
  tr AS (
    SELECT *, ST_GEOGPOINT(tract_lon, tract_lat) AS tg
    FROM `qwiklabs-gcp-04-ec3596addc43.a4i_ml.tracts_enriched`
  ),
  nearest AS (
    SELECT
      p.point_id,
      ARRAY_AGG(
        STRUCT(
          tr.geo_id,
          tr.median_year_built,
          tr.pop_density_km2,
          tr.housing_density_km2,
          tr.water_share,
          ST_DISTANCE(p.g, tr.tg) AS meters
        )
        ORDER BY ST_DISTANCE(p.g, tr.tg)
        LIMIT 1
      )[OFFSET(0)] AS nt
    FROM p
    JOIN tr
      ON ST_DWITHIN(p.g, tr.tg, 5000)
    GROUP BY p.point_id
  ),
  ring AS (
    SELECT
      p.point_id,
      SUM(tr.total_pop) AS pop_within_1500m,
      SUM(tr.housing_units) AS housing_within_1500m,
      AVG(tr.median_year_built) AS mean_year_built_1500m
    FROM p
    JOIN tr
      ON ST_DWITHIN(p.g, tr.tg, 1500)
    GROUP BY p.point_id
  )
  SELECT
    p.point_id,
    p.lat,
    p.lon,
    n.nt.geo_id AS geo_id,
    ST_COVERS(f.footprint, p.g) AS in_footprint,
    n.nt.meters AS meters_to_tract_point,
    -- Model features (physical / built environment only)
    ST_DISTANCE(p.g, f.center) / 1000.0 AS km_from_center,
    n.nt.median_year_built AS median_year_built,
    n.nt.pop_density_km2 AS pop_density_km2,
    n.nt.housing_density_km2 AS housing_density_km2,
    COALESCE(n.nt.water_share, 0.0) AS water_share,
    COALESCE(r.pop_within_1500m, 0.0) AS pop_within_1500m,
    COALESCE(r.housing_within_1500m, 0.0) AS housing_within_1500m,
    r.mean_year_built_1500m AS mean_year_built_1500m
  FROM p
  CROSS JOIN `qwiklabs-gcp-04-ec3596addc43.a4i_ml.campaign_footprint` f
  LEFT JOIN nearest n USING (point_id)
  LEFT JOIN ring r USING (point_id)
);
