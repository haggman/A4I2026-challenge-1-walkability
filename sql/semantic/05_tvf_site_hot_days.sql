-- sql/semantic/05_tvf_site_hot_days.sql
-- Purpose : Table-valued function computing mean days/year a site with heat offset `offset_f` (°F above city mean)
--           experiences >= 95°F-equivalent heat (`city_max_temp_f >= 95 - offset_f`).
-- Inputs  : Parameter `offset_f FLOAT64`; reads `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_city_heat_day`
-- Outputs : Table Function `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.site_hot_days(offset_f FLOAT64)`
-- Owner   : data lane
-- Why     : Translates a spatial heat offset (+°F above city mean) into an intuitive frequency metric for council
--           members ("at a +3.5°F offset site, residents experience 95°F-equivalent heat on X days/year vs Y city-wide").
--
-- Example query:
--   SELECT * FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.site_hot_days`(3.5);

CREATE OR REPLACE TABLE FUNCTION `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.site_hot_days`(
  offset_f FLOAT64
)
OPTIONS (
  description = 'Returns mean annual days (across full years >=300 days, 2019-2025) where a site with heat offset offset_f (deg F above city mean) reaches 95 deg F equivalent heat (city_max_temp_f >= 95 - offset_f), compared against the city-wide baseline (offset = 0).'
) AS (
  WITH yearly AS (
    SELECT
      EXTRACT(YEAR FROM date) AS year,
      COUNT(*) AS days_reported,
      COUNTIF(city_max_temp_f >= 95.0 - offset_f) AS site_days_ge_95f_equiv,
      COUNTIF(city_max_temp_f >= 95.0) AS city_days_ge_95f,
      COUNTIF(city_max_temp_f >= 90.0 - offset_f) AS site_days_ge_90f_equiv,
      COUNTIF(city_max_temp_f >= 100.0 - offset_f) AS site_days_ge_100f_equiv
    FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_city_heat_day`
    GROUP BY year
    HAVING days_reported >= 300
  )
  SELECT
    ROUND(offset_f, 2) AS offset_f,
    ROUND(95.0 - offset_f, 2) AS station_threshold_for_95f_equiv,
    ROUND(AVG(site_days_ge_95f_equiv), 1) AS mean_days_ge_95f_equiv_per_yr,
    ROUND(AVG(city_days_ge_95f), 1) AS city_baseline_days_ge_95f_per_yr,
    ROUND(AVG(site_days_ge_95f_equiv) - AVG(city_days_ge_95f), 1) AS extra_days_ge_95f_equiv_per_yr,
    ROUND(AVG(site_days_ge_90f_equiv), 1) AS mean_days_ge_90f_equiv_per_yr,
    ROUND(AVG(site_days_ge_100f_equiv), 1) AS mean_days_ge_100f_equiv_per_yr,
    COUNT(*) AS full_years_counted
  FROM yearly
);
