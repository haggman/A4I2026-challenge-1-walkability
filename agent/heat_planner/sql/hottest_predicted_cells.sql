SELECT
  point_id,
  ROUND(lat, 5) AS lat,
  ROUND(lon, 5) AS lon,
  geo_id,
  ROUND(predicted_offset_f, 2) AS predicted_offset_f,
  unmeasured,
  total_pop,
  pop_65_plus,
  ROUND(share_65_plus, 4) AS share_65_plus,
  car_free_households,
  ROUND(no_vehicle_rate, 4) AS no_vehicle_rate,
  ROUND(poverty_rate, 4) AS poverty_rate,
  ROUND(median_income, 0) AS median_income,
  model_version
FROM `PROJECT.a4i_ml.grid_predictions`
WHERE (NOT @unmeasured_only OR unmeasured)
ORDER BY predicted_offset_f DESC
LIMIT @limit
