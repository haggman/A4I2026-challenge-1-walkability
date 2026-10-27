SELECT
  query_lat,
  query_lon,
  radius_m,
  tracts_within_radius,
  population_within_radius,
  pop_65_plus_within_radius,
  car_free_households_within_radius,
  households_within_radius,
  ROUND(share_65_plus_within_radius, 4) AS share_65_plus_within_radius,
  ROUND(no_vehicle_rate_within_radius, 4) AS no_vehicle_rate_within_radius,
  ROUND(pop_weighted_poverty_rate, 4) AS pop_weighted_poverty_rate,
  TO_JSON_STRING(tract_geo_ids) AS tract_geo_ids_json
FROM `PROJECT.a4i_semantic.vulnerable_population`(
  @lat, @lon, LEAST(GREATEST(@radius_m, 100.0), 5000.0)
)
LIMIT 1
