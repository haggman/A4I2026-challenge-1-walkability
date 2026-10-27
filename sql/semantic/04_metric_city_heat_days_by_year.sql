-- sql/semantic/04_metric_city_heat_days_by_year.sql
-- Purpose : Annual count of hot days (>=90 F, >=95 F, >=100 F) in Atlanta for full years (>=300 days reported),
--           with multi-year means and OLS slope.
-- Inputs  : `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_city_heat_day`
-- Outputs : `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.metric_city_heat_days_by_year`
-- Owner   : data lane
-- Why     : Powers the agent tool `get_heat_frequency` / `city_heat_days_by_year` and the pitch deck's
--           historical heat-frequency chart. Restricts to years with >=300 reported days so partial years
--           cannot distort annual counts or slopes.
--           CAVEAT: 7 years (2019-2025) captures inter-annual weather variability, NOT a long-term climate trend.
--
-- Example query:
--   SELECT year, days_ge_90_f, days_ge_95_f, days_ge_100_f, mean_days_ge_95_f, ols_slope_days_ge_95_per_yr
--   FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.metric_city_heat_days_by_year`
--   ORDER BY year;

CREATE OR REPLACE VIEW `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.metric_city_heat_days_by_year`
(
  year OPTIONS (description = 'Calendar year (INT64, full years with >=300 reporting days only).'),
  days_reported OPTIONS (description = 'Number of calendar days with station coverage in the year (days, >=300).'),
  days_ge_90_f OPTIONS (description = 'Days in the year when city_max_temp_f reached >= 90 deg F (days).'),
  days_ge_95_f OPTIONS (description = 'Days in the year when city_max_temp_f reached >= 95 deg F (days).'),
  days_ge_100_f OPTIONS (description = 'Days in the year when city_max_temp_f reached >= 100 deg F (days).'),
  hottest_temp_f OPTIONS (description = 'Highest station daily maximum temperature recorded in the year (deg F).'),
  mean_days_ge_90_f OPTIONS (description = 'Multi-year mean of annual days >= 90 deg F across full years (days/yr).'),
  mean_days_ge_95_f OPTIONS (description = 'Multi-year mean of annual days >= 95 deg F across full years (days/yr).'),
  mean_days_ge_100_f OPTIONS (description = 'Multi-year mean of annual days >= 100 deg F across full years (days/yr).'),
  ols_slope_days_ge_95_per_yr OPTIONS (description = 'OLS linear slope of annual days >= 95 deg F per year (days/yr/yr; caveat: 7 years reflects weather variability, not a climate trend).')
)
OPTIONS (
  description = 'Annual hot-day counts (>=90 F, >=95 F, >=100 F), multi-year means, and OLS slope for Atlanta (2019-2025, full years >=300 days). Caveat: 7 years represents weather variability, not a long-term climate trend.',
  labels = [('app', 'heat-planner'), ('lane', 'data'), ('layer', 'semantic')]
) AS
WITH yearly AS (
  SELECT
    EXTRACT(YEAR FROM date) AS year,
    COUNT(*) AS days_reported,
    COUNTIF(city_max_temp_f >= 90) AS days_ge_90_f,
    COUNTIF(city_max_temp_f >= 95) AS days_ge_95_f,
    COUNTIF(city_max_temp_f >= 100) AS days_ge_100_f,
    MAX(city_max_temp_f) AS hottest_temp_f
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_city_heat_day`
  GROUP BY year
  HAVING days_reported >= 300
)
SELECT
  y.year,
  y.days_reported,
  y.days_ge_90_f,
  y.days_ge_95_f,
  y.days_ge_100_f,
  y.hottest_temp_f,
  ROUND(AVG(y.days_ge_90_f) OVER (), 1) AS mean_days_ge_90_f,
  ROUND(AVG(y.days_ge_95_f) OVER (), 1) AS mean_days_ge_95_f,
  ROUND(AVG(y.days_ge_100_f) OVER (), 1) AS mean_days_ge_100_f,
  ROUND(
    SAFE_DIVIDE(
      COVAR_POP(CAST(y.days_ge_95_f AS FLOAT64), CAST(y.year AS FLOAT64)) OVER (),
      VAR_POP(CAST(y.year AS FLOAT64)) OVER ()
    ),
    2
  ) AS ols_slope_days_ge_95_per_yr
FROM yearly y;
