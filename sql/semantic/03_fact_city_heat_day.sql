-- sql/semantic/03_fact_city_heat_day.sql
-- Purpose : City-wide daily maximum temperature across Atlanta GHCN weather stations (one row per calendar date).
-- Inputs  : `qwiklabs-gcp-04-ec3596addc43.a4i_core.station_days`
-- Outputs : `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_city_heat_day`
-- Owner   : data lane
-- Why     : Taking MAX(max_temp_f) across official GHCN stations for each date measures whether anywhere in
--           official Atlanta weather records reached a heat threshold on that day, avoiding bias from varying
--           numbers of reporting stations across years.
--
-- Example query:
--   SELECT date, city_max_temp_f, n_stations_reporting
--   FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_city_heat_day`
--   WHERE city_max_temp_f >= 95
--   ORDER BY date DESC
--   LIMIT 10;

CREATE OR REPLACE VIEW `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_city_heat_day`
(
  date OPTIONS (description = 'Calendar date of observation (DATE, 2019-01-01 to 2025-12-31).'),
  city_max_temp_f OPTIONS (description = 'Maximum daily air temperature recorded across all reporting Atlanta GHCN stations on that date (deg F).'),
  city_mean_station_max_temp_f OPTIONS (description = 'Mean of daily maximum air temperatures across reporting Atlanta GHCN stations on that date (deg F).'),
  n_stations_reporting OPTIONS (description = 'Number of Atlanta GHCN stations reporting on that date (count).')
)
OPTIONS (
  description = 'Daily city-wide maximum temperature across Atlanta GHCN stations (one row per date, 2,557 days across 2019-2025). Answers how often the city experiences extreme heat.',
  labels = [('app', 'heat-planner'), ('lane', 'data'), ('layer', 'semantic')]
) AS
SELECT
  observation_date AS date,
  MAX(max_temp_f) AS city_max_temp_f,
  ROUND(AVG(max_temp_f), 2) AS city_mean_station_max_temp_f,
  COUNT(DISTINCT station_id) AS n_stations_reporting
FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.station_days`
GROUP BY observation_date;
