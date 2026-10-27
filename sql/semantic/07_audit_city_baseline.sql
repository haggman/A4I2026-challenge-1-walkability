-- sql/semantic/07_audit_city_baseline.sql
-- Purpose : Population-weighted city-wide baseline metrics across all populated Atlanta census tracts for the post-hoc equity audit.
-- Inputs  : `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`
-- Outputs : `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.audit_city_baseline`
-- Owner   : data lane
-- Why     : Provides the sentinel-free, population-weighted city denominator for `run_equity_audit`
--           (comparing recommended cooling-center tracts against the city on median income, poverty rate,
--           no-vehicle rate, share 65+, median age, and share in top-quintile poverty tracts).
--           Output check only; never used as model input.
--
-- Example query:
--   SELECT * FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.audit_city_baseline`;

CREATE OR REPLACE VIEW `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.audit_city_baseline`
(
  populated_tracts OPTIONS (description = 'Number of census tracts with total_pop > 0 included in the city baseline (tracts).'),
  total_population OPTIONS (description = 'Total resident population across all tracts (persons).'),
  total_pop_65_plus OPTIONS (description = 'Total residents aged 65+ across all tracts (persons).'),
  total_car_free_households OPTIONS (description = 'Total car-free households across all tracts (households).'),
  city_median_income_usd OPTIONS (description = 'Population-weighted mean of tract median household income across populated tracts with non-null income (USD).'),
  city_poverty_rate OPTIONS (description = 'Population-weighted poverty rate across populated tracts (share 0-1).'),
  city_no_vehicle_rate OPTIONS (description = 'Population-weighted no-vehicle household rate across populated tracts (share 0-1).'),
  city_share_65_plus OPTIONS (description = 'Population-weighted share of residents aged 65 years and older (share 0-1).'),
  city_median_age_years OPTIONS (description = 'Population-weighted mean of tract median age across populated tracts (years).'),
  city_share_in_top_poverty_quintile OPTIONS (description = 'Share of city population living in the top quintile (top 20%) of tracts by poverty_rate (share 0-1).'),
  top_poverty_quintile_threshold OPTIONS (description = 'Minimum tract poverty_rate for the top poverty quintile (share 0-1).')
)
OPTIONS (
  description = 'Population-weighted city-wide baseline metrics across populated Atlanta census tracts (350 populated tracts, 1,447,970 residents) for the post-hoc equity audit.',
  labels = [('app', 'heat-planner'), ('lane', 'data'), ('layer', 'semantic')]
) AS
WITH ranked AS (
  SELECT
    geo_id,
    total_pop,
    pop_65_plus,
    no_cars,
    median_income,
    poverty_rate,
    no_vehicle_rate,
    median_age,
    NTILE(5) OVER (ORDER BY poverty_rate) = 5 AS is_top_poverty_quintile
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`
  WHERE total_pop > 0
)
SELECT
  COUNT(*) AS populated_tracts,
  ROUND(SUM(total_pop), 0) AS total_population,
  ROUND(SUM(pop_65_plus), 0) AS total_pop_65_plus,
  ROUND(SUM(no_cars), 0) AS total_car_free_households,
  ROUND(SAFE_DIVIDE(SUM(total_pop * median_income), SUM(IF(median_income IS NULL, 0, total_pop))), 2) AS city_median_income_usd,
  ROUND(SAFE_DIVIDE(SUM(total_pop * poverty_rate), SUM(IF(poverty_rate IS NULL, 0, total_pop))), 4) AS city_poverty_rate,
  ROUND(SAFE_DIVIDE(SUM(total_pop * no_vehicle_rate), SUM(IF(no_vehicle_rate IS NULL, 0, total_pop))), 4) AS city_no_vehicle_rate,
  ROUND(SAFE_DIVIDE(SUM(pop_65_plus), SUM(total_pop)), 4) AS city_share_65_plus,
  ROUND(SAFE_DIVIDE(SUM(total_pop * median_age), SUM(IF(median_age IS NULL, 0, total_pop))), 2) AS city_median_age_years,
  ROUND(SAFE_DIVIDE(SUM(IF(is_top_poverty_quintile, total_pop, 0)), SUM(total_pop)), 4) AS city_share_in_top_poverty_quintile,
  ROUND(MIN(IF(is_top_poverty_quintile, poverty_rate, NULL)), 4) AS top_poverty_quintile_threshold
FROM ranked;
