-- heat_frequency.sql: "How often does this city hit dangerous heat, and is it moving?"
-- Purpose : GHCN station history → per-year counts of hot days + a simple linear slope.
-- Inputs  : PROJECT.a4i_climate.station_daily_temps
-- Output  : per-year rows + slope columns (repeated) for days >= 95F
-- Owner   : data lane. Agent tool `get_heat_frequency` wraps this.
-- Caveat  : ~7 years is variability, not a climate trend. Report slope with that caveat.
--
-- Method: for each date, take the MAX across stations (city-wide "did anywhere official hit X"),
-- which avoids penalizing years with more/fewer reporting stations.

WITH daily AS (
  SELECT observation_date AS d, MAX(max_temp_f) AS tmax_f
  FROM `PROJECT.a4i_climate.station_daily_temps`
  GROUP BY d
),
yearly AS (
  SELECT
    EXTRACT(YEAR FROM d) AS yr,
    COUNT(*) AS days_reported,
    COUNTIF(tmax_f >= 90)  AS days_ge_90,
    COUNTIF(tmax_f >= 95)  AS days_ge_95,
    COUNTIF(tmax_f >= 100) AS days_ge_100,
    MAX(tmax_f) AS hottest_f
  FROM daily
  GROUP BY yr
  HAVING days_reported >= 300          -- drop partial years so counts are comparable
)
SELECT
  y.*,
  ROUND(AVG(days_ge_95) OVER (), 1) AS mean_days_ge_95,
  -- OLS slope of days_ge_95 on year
  ROUND(
    SAFE_DIVIDE(
      COVAR_POP(days_ge_95, yr) OVER (),
      VAR_POP(yr) OVER ()), 2) AS slope_days_ge_95_per_year
FROM yearly y
ORDER BY yr;
