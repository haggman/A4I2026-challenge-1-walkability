-- a4i_grid.heat_reference_daily, a4i_grid.city_heat_history
-- HEAT LAYER, time. Heat Watch is one afternoon; GHCN stations give the history.
--
-- Reference daily high = average TMAX of the three in-city NOAA stations with a full
-- 2019-2025 record: Central Park, LaGuardia, JFK. Newark and the NJ stations are left out
-- because they run hotter inland and aren't in the area the campaign drove.

CREATE OR REPLACE TABLE a4i_grid.heat_reference_daily AS
SELECT
  observation_date,
  AVG(max_temp_f)  AS ref_max_temp_f,
  COUNT(*)         AS n_stations
FROM a4i_brooklyn.station_daily_temps
WHERE station_id IN ('USW00094728',   -- NY CITY CNTRL PARK
                     'USW00014732',   -- LAGUARDIA AP
                     'USW00094789')   -- JFK INTL AP
GROUP BY observation_date;

CREATE OR REPLACE TABLE a4i_grid.city_heat_history AS
SELECT
  EXTRACT(YEAR FROM observation_date)  AS year,
  COUNT(*)                             AS days_observed,
  COUNTIF(ref_max_temp_f >= 90)        AS days_ge_90,
  COUNTIF(ref_max_temp_f >= 95)        AS days_ge_95,
  COUNTIF(ref_max_temp_f >= 100)       AS days_ge_100,
  MAX(ref_max_temp_f)                  AS peak_f
FROM a4i_grid.heat_reference_daily
GROUP BY year;
