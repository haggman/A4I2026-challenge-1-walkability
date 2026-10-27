-- sql/core/01_heat_readings.sql
-- Purpose : Clean, type, and enrich raw Heat Watch mobile traverse readings into one-row-per-reading core table.
-- Inputs  : `qwiklabs-gcp-04-ec3596addc43.a4i_climate.heat_observations`
-- Outputs : `qwiklabs-gcp-04-ec3596addc43.a4i_core.heat_readings`
-- Owner   : data lane
-- Why     : Raw heat_observations has NULL city labels (23,386/23,386), 4,052 4-decimal near-duplicates,
--           and 526 readings where the traverse vehicle was stationary (>=10 neighbors within 20 m).
--           We populate city='Atlanta', enforce 40-140 F and sentinel guards, attach geohash-7 cell_id,
--           and flag (rather than delete) stationary clusters and +-4 SD temperature outliers so
--           downstream exclusion in a4i_semantic.fact_heat_cell is transparent and reversible.

CREATE OR REPLACE TABLE `qwiklabs-gcp-04-ec3596addc43.a4i_core.heat_readings`
OPTIONS (
  description = 'Cleaned Heat Watch mobile traverse readings for Atlanta (one row per 1 Hz reading, range-checked 40-140 deg F, with reversible stationary-cluster and +-4 SD outlier boolean flags).',
  labels = [('app', 'heat-planner'), ('lane', 'data'), ('layer', 'core')]
) AS
WITH typed AS (
  SELECT
    ROW_NUMBER() OVER (ORDER BY observed_at, latitude, longitude, temp_f) AS rn,
    COALESCE(NULLIF(TRIM(CAST(city AS STRING)), ''), 'Atlanta') AS city,
    SAFE_CAST(latitude AS FLOAT64) AS latitude,
    SAFE_CAST(longitude AS FLOAT64) AS longitude,
    ST_GEOGPOINT(SAFE_CAST(longitude AS FLOAT64), SAFE_CAST(latitude AS FLOAT64)) AS geog,
    ST_GEOHASH(ST_GEOGPOINT(SAFE_CAST(longitude AS FLOAT64), SAFE_CAST(latitude AS FLOAT64)), 7) AS cell_id,
    SAFE_CAST(temp_f AS FLOAT64) AS temp_f,
    IF(SAFE_CAST(heat_index_f AS FLOAT64) BETWEEN 40 AND 160
       AND SAFE_CAST(heat_index_f AS FLOAT64) NOT IN (-9999, -999, 9999.9),
       SAFE_CAST(heat_index_f AS FLOAT64), NULL) AS heat_index_f,
    IF(SAFE_CAST(humidity_pct AS FLOAT64) BETWEEN 0 AND 100
       AND SAFE_CAST(humidity_pct AS FLOAT64) NOT IN (-9999, -999, 9999.9),
       SAFE_CAST(humidity_pct AS FLOAT64), NULL) AS humidity_pct,
    observed_at
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_climate.heat_observations`
  WHERE latitude IS NOT NULL
    AND longitude IS NOT NULL
    AND SAFE_CAST(latitude AS FLOAT64) BETWEEN -90 AND 90
    AND SAFE_CAST(longitude AS FLOAT64) BETWEEN -180 AND 180
    AND temp_f IS NOT NULL
    AND SAFE_CAST(temp_f AS FLOAT64) BETWEEN 40 AND 140
    AND SAFE_CAST(temp_f AS FLOAT64) NOT IN (-9999, -999, 9999.9)
),
stats AS (
  SELECT
    AVG(temp_f) AS mean_temp_f,
    STDDEV(temp_f) AS sd_temp_f
  FROM typed
),
neighbors AS (
  SELECT
    a.rn,
    COUNT(*) - 1 AS neighbors_within_20m
  FROM typed a
  JOIN typed b
    ON ST_DWITHIN(a.geog, b.geog, 20)
  GROUP BY a.rn
)
SELECT
  FORMAT('atl_hr_%05d', t.rn) AS reading_id,
  t.city,
  t.latitude,
  t.longitude,
  t.geog,
  t.cell_id,
  t.temp_f,
  t.heat_index_f,
  t.humidity_pct,
  t.observed_at,
  n.neighbors_within_20m,
  (n.neighbors_within_20m >= 10) AS is_stationary_cluster,
  ROUND(SAFE_DIVIDE(t.temp_f - s.mean_temp_f, s.sd_temp_f), 4) AS temp_zscore,
  (ABS(t.temp_f - s.mean_temp_f) > 4 * s.sd_temp_f) AS is_temp_outlier
FROM typed t
JOIN neighbors n USING (rn)
CROSS JOIN stats s;

ALTER TABLE `qwiklabs-gcp-04-ec3596addc43.a4i_core.heat_readings`
  ALTER COLUMN reading_id SET OPTIONS (description = 'Deterministic unique identifier for the traverse reading (string, atl_hr_NNNNN).'),
  ALTER COLUMN city SET OPTIONS (description = 'Campaign city name (string, populated as Atlanta where raw was NULL).'),
  ALTER COLUMN latitude SET OPTIONS (description = 'Reading latitude (degrees North, WGS84).'),
  ALTER COLUMN longitude SET OPTIONS (description = 'Reading longitude (degrees East, WGS84).'),
  ALTER COLUMN geog SET OPTIONS (description = 'Point geography of reading (GEOGRAPHY, ST_GEOGPOINT(longitude, latitude)).'),
  ALTER COLUMN cell_id SET OPTIONS (description = 'Geohash-7 spatial cell identifier (~153 m x 153 m).'),
  ALTER COLUMN temp_f SET OPTIONS (description = 'Drive-day ambient air temperature (deg F, range-checked 40-140 deg F; label-side only, never a model feature).'),
  ALTER COLUMN heat_index_f SET OPTIONS (description = 'Drive-day heat index (deg F, 40-160 deg F or NULL; never a model feature).'),
  ALTER COLUMN humidity_pct SET OPTIONS (description = 'Drive-day relative humidity (%, 0-100 or NULL; never a model feature).'),
  ALTER COLUMN observed_at SET OPTIONS (description = 'Drive-day reading timestamp (UTC TIMESTAMP; never a model feature).'),
  ALTER COLUMN neighbors_within_20m SET OPTIONS (description = 'Wait-spot density: count of other traverse readings within 20 meters (count).'),
  ALTER COLUMN is_stationary_cluster SET OPTIONS (description = 'Reversible boolean flag: TRUE when >=10 other readings fall within 20 m (stationary vehicle cluster).'),
  ALTER COLUMN temp_zscore SET OPTIONS (description = 'Standardized temperature z-score relative to the campaign mean (SD units).'),
  ALTER COLUMN is_temp_outlier SET OPTIONS (description = 'Reversible boolean flag: TRUE when temp_f is beyond +-4 SD from the campaign mean.');
