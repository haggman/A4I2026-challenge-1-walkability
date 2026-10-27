-- validate.sql: table-level health checks for a4i_climate.
-- Purpose : prove the loaded tables are sane before anyone trains on them.
-- Inputs  : PROJECT.a4i_climate.{heat_observations, station_daily_temps, tract_demographics}
-- Output  : one row per check: check_name, passed, detail
-- Owner   : data lane
-- Replace PROJECT with your project id (or run unqualified from the project's default).

WITH h AS (
  SELECT
    COUNT(*) AS n,
    MIN(temp_f) AS tmin, MAX(temp_f) AS tmax,
    MIN(humidity_pct) AS rhmin, MAX(humidity_pct) AS rhmax,
    MIN(heat_index_f) AS himin,
    COUNTIF(city IS NULL) AS null_city,
    COUNTIF(observed_at IS NULL) AS null_time,
    COUNT(DISTINCT FORMAT('%.4f,%.4f', latitude, longitude)) AS pts,
    AVG(longitude) AS clon, AVG(latitude) AS clat
  FROM `PROJECT.a4i_climate.heat_observations`
),
s AS (
  SELECT COUNT(*) AS n, COUNT(DISTINCT station_id) AS stations,
         MIN(observation_date) AS d0, MAX(observation_date) AS d1,
         MIN(max_temp_f) AS tmin, MAX(max_temp_f) AS tmax
  FROM `PROJECT.a4i_climate.station_daily_temps`
),
near AS (
  SELECT MIN(ST_DISTANCE(ST_GEOGPOINT(st.longitude, st.latitude),
                         ST_GEOGPOINT(h.clon, h.clat))) / 1000 AS km
  FROM (SELECT DISTINCT station_id, latitude, longitude
        FROM `PROJECT.a4i_climate.station_daily_temps`) st, h
),
t AS (
  SELECT COUNT(*) AS n,
         COUNTIF(LENGTH(geo_id) != 11) AS bad_geoid,
         COUNTIF(poverty_rate < 0 OR poverty_rate > 1) AS bad_pov,
         COUNTIF(tract_lat IS NULL OR tract_lon IS NULL) AS null_xy,
         SUM(total_pop) AS people
  FROM `PROJECT.a4i_climate.tract_demographics`
)
SELECT * FROM UNNEST([
  STRUCT('heat: has rows' AS check_name, (SELECT n > 1000 FROM h) AS passed,
         FORMAT('%d rows', (SELECT n FROM h)) AS detail),
  ('heat: temp 40-140F', (SELECT tmin >= 40 AND tmax <= 140 FROM h),
         (SELECT FORMAT('%.1f..%.1f', tmin, tmax) FROM h)),
  ('heat: no sentinel survivors',
         (SELECT COALESCE(tmin,0) > -100 AND COALESCE(himin,0) > -100 AND COALESCE(rhmin,0) > -100 FROM h),
         (SELECT FORMAT('min temp %.1f, hi %t, rh %t', tmin, himin, rhmin) FROM h)),
  ('heat: humidity 0-100 or null', (SELECT rhmin IS NULL OR (rhmin >= 0 AND rhmax <= 100) FROM h),
         (SELECT FORMAT('%t..%t', rhmin, rhmax) FROM h)),
  ('heat: city label present', (SELECT null_city = 0 FROM h), (SELECT FORMAT('%d null', null_city) FROM h)),
  ('heat: spatially spread', (SELECT pts > 500 FROM h), (SELECT FORMAT('%d distinct points', pts) FROM h)),
  ('heat: intra-city spread > 3F', (SELECT tmax - tmin > 3 FROM h), (SELECT FORMAT('%.1f F', tmax - tmin) FROM h)),
  ('heat: timestamp coverage (info only)', TRUE,
         (SELECT FORMAT('%.0f%% have observed_at', 100 * (1 - SAFE_DIVIDE(null_time, n))) FROM h)),
  ('stations: has rows', (SELECT n > 0 FROM s), (SELECT FORMAT('%d station-days, %d stations', n, stations) FROM s)),
  ('stations: multi-year', (SELECT DATE_DIFF(d1, d0, DAY) > 365 FROM s), (SELECT FORMAT('%t..%t', d0, d1) FROM s)),
  ('stations: temp sane', (SELECT tmin >= -60 AND tmax <= 140 FROM s), (SELECT FORMAT('%.0f..%.0f', tmin, tmax) FROM s)),
  ('cross: station < 40km from traverses', (SELECT km < 40 FROM near), (SELECT FORMAT('%.1f km', km) FROM near)),
  ('tracts: has rows', (SELECT n > 0 FROM t), (SELECT FORMAT('%d tracts, %.0f people', n, people) FROM t)),
  ('tracts: geo_id 11 chars', (SELECT bad_geoid = 0 FROM t), (SELECT FORMAT('%d malformed', bad_geoid) FROM t)),
  ('tracts: poverty_rate 0-1', (SELECT bad_pov = 0 FROM t), (SELECT FORMAT('%d out of range', bad_pov) FROM t)),
  ('tracts: coords present', (SELECT null_xy = 0 FROM t), (SELECT FORMAT('%d missing', null_xy) FROM t))
]);
