SELECT
  geo_id,
  centroid_lat,
  centroid_lon,
  ROUND(ST_DISTANCE(ST_GEOGPOINT(centroid_lon, centroid_lat), ST_GEOGPOINT(@lon, @lat)), 0) AS meters_to_tract_center,
  population,
  pop_65_plus,
  ROUND(share_65_plus, 4) AS share_65_plus,
  car_free_households,
  households,
  housing_units,
  ROUND(no_vehicle_rate, 4) AS no_vehicle_rate,
  ROUND(poverty_rate, 4) AS poverty_rate,
  ROUND(median_income, 0) AS median_income,
  ROUND(median_age, 1) AS median_age,
  median_year_built,
  ROUND(pop_density_km2, 1) AS pop_density_km2,
  ROUND(housing_density_km2, 1) AS housing_density_km2,
  ROUND(water_share, 4) AS water_share
FROM `PROJECT.a4i_semantic.dim_tract`
ORDER BY meters_to_tract_center
LIMIT 1
