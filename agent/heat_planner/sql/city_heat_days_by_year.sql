SELECT
  year,
  days_reported,
  days_ge_90_f,
  days_ge_95_f,
  days_ge_100_f,
  hottest_temp_f,
  mean_days_ge_90_f,
  mean_days_ge_95_f,
  mean_days_ge_100_f,
  ols_slope_days_ge_95_per_yr
FROM `PROJECT.a4i_semantic.metric_city_heat_days_by_year`
ORDER BY year
LIMIT 20
