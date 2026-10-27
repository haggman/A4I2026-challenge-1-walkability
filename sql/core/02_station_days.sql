-- sql/core/02_station_days.sql
-- Purpose : Clean, deduplicate, and enrich GHCN daily station temperatures with distance to Atlanta campaign centroid.
-- Inputs  : `qwiklabs-gcp-04-ec3596addc43.a4i_climate.station_daily_temps`,
--           `qwiklabs-gcp-04-ec3596addc43.a4i_climate.heat_observations`
-- Outputs : `qwiklabs-gcp-04-ec3596addc43.a4i_core.station_days`
-- Owner   : data lane
-- Why     : Enforces one-row-per-station-per-day grain, verifies temperature range (-60 to 140 F) with no
--           surviving sentinels, and attaches straight-line distance (km) from each GHCN station to the
--           Atlanta Heat Watch traverse centroid so station proximity (<40 km) is documented in the table.

CREATE OR REPLACE TABLE `qwiklabs-gcp-04-ec3596addc43.a4i_core.station_days`
OPTIONS (
  description = 'Cleaned GHCN daily maximum temperatures for Atlanta-area weather stations (one row per station_id per observation_date, with distance in km to the Heat Watch campaign centroid).',
  labels = [('app', 'heat-planner'), ('lane', 'data'), ('layer', 'core')]
) AS
WITH campaign_center AS (
  SELECT
    ST_GEOGPOINT(AVG(SAFE_CAST(longitude AS FLOAT64)), AVG(SAFE_CAST(latitude AS FLOAT64))) AS center_geog
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_climate.heat_observations`
  WHERE latitude IS NOT NULL AND longitude IS NOT NULL
),
deduped AS (
  SELECT
    TRIM(CAST(station_id AS STRING)) AS station_id,
    TRIM(CAST(station_name AS STRING)) AS station_name,
    SAFE_CAST(observation_date AS DATE) AS observation_date,
    SAFE_CAST(latitude AS FLOAT64) AS latitude,
    SAFE_CAST(longitude AS FLOAT64) AS longitude,
    ST_GEOGPOINT(SAFE_CAST(longitude AS FLOAT64), SAFE_CAST(latitude AS FLOAT64)) AS station_geog,
    SAFE_CAST(max_temp_f AS FLOAT64) AS max_temp_f
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_climate.station_daily_temps`
  WHERE station_id IS NOT NULL
    AND observation_date IS NOT NULL
    AND latitude IS NOT NULL
    AND longitude IS NOT NULL
    AND max_temp_f IS NOT NULL
    AND SAFE_CAST(max_temp_f AS FLOAT64) BETWEEN -60 AND 140
    AND SAFE_CAST(max_temp_f AS FLOAT64) NOT IN (-9999, -999, 9999.9)
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY TRIM(CAST(station_id AS STRING)), SAFE_CAST(observation_date AS DATE)
    ORDER BY SAFE_CAST(max_temp_f AS FLOAT64) DESC
  ) = 1
)
SELECT
  d.station_id,
  d.station_name,
  d.observation_date,
  d.latitude,
  d.longitude,
  d.station_geog,
  d.max_temp_f,
  ROUND(ST_DISTANCE(d.station_geog, c.center_geog) / 1000.0, 3) AS dist_to_campaign_center_km
FROM deduped d
CROSS JOIN campaign_center c;

ALTER TABLE `qwiklabs-gcp-04-ec3596addc43.a4i_core.station_days`
  ALTER COLUMN station_id SET OPTIONS (description = 'GHCN-Daily weather station identifier (string, e.g., USW00013874).'),
  ALTER COLUMN station_name SET OPTIONS (description = 'Official NOAA GHCN weather station name (string).'),
  ALTER COLUMN observation_date SET OPTIONS (description = 'Calendar date of daily maximum temperature reading (DATE).'),
  ALTER COLUMN latitude SET OPTIONS (description = 'Station latitude (degrees North, WGS84).'),
  ALTER COLUMN longitude SET OPTIONS (description = 'Station longitude (degrees East, WGS84).'),
  ALTER COLUMN station_geog SET OPTIONS (description = 'Point geography of weather station (GEOGRAPHY, ST_GEOGPOINT(longitude, latitude)).'),
  ALTER COLUMN max_temp_f SET OPTIONS (description = 'Daily maximum air temperature recorded at station (deg F, range-checked -60 to 140 deg F).'),
  ALTER COLUMN dist_to_campaign_center_km SET OPTIONS (description = 'Straight-line distance from station to the Atlanta Heat Watch traverse centroid (km).');
