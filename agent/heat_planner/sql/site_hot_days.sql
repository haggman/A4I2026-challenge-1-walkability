SELECT
  offset_f,
  station_threshold_for_95f_equiv,
  mean_days_ge_95f_equiv_per_yr,
  city_baseline_days_ge_95f_per_yr,
  extra_days_ge_95f_equiv_per_yr,
  mean_days_ge_90f_equiv_per_yr,
  mean_days_ge_100f_equiv_per_yr,
  full_years_counted
FROM `PROJECT.a4i_semantic.site_hot_days`(
  LEAST(GREATEST(@offset_f, -10.0), 15.0)
)
LIMIT 1
