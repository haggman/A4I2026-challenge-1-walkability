SELECT
  populated_tracts,
  total_population,
  total_pop_65_plus,
  total_car_free_households,
  ROUND(city_median_income_usd, 0) AS city_median_income_usd,
  ROUND(city_poverty_rate, 4) AS city_poverty_rate,
  ROUND(city_no_vehicle_rate, 4) AS city_no_vehicle_rate,
  ROUND(city_share_65_plus, 4) AS city_share_65_plus,
  ROUND(city_median_age_years, 2) AS city_median_age_years,
  ROUND(city_share_in_top_poverty_quintile, 4) AS city_share_in_top_poverty_quintile,
  ROUND(top_poverty_quintile_threshold, 4) AS top_poverty_quintile_threshold
FROM `PROJECT.a4i_semantic.audit_city_baseline`
LIMIT 1
