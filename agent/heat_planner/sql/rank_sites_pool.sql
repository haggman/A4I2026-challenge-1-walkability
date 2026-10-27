WITH z AS (
  SELECT
    *,
    (predicted_offset_f - AVG(predicted_offset_f) OVER ()) / NULLIF(STDDEV(predicted_offset_f) OVER (), 0) AS z_hazard,
    (no_vehicle_rate    - AVG(no_vehicle_rate)    OVER ()) / NULLIF(STDDEV(no_vehicle_rate)    OVER (), 0) AS z_novehicle,
    (share_65_plus      - AVG(share_65_plus)      OVER ()) / NULLIF(STDDEV(share_65_plus)      OVER (), 0) AS z_age65,
    (poverty_rate       - AVG(poverty_rate)       OVER ()) / NULLIF(STDDEV(poverty_rate)       OVER (), 0) AS z_poverty,
    (total_pop          - AVG(total_pop)          OVER ()) / NULLIF(STDDEV(total_pop)          OVER (), 0) AS z_pop
  FROM `PROJECT.a4i_ml.grid_predictions`
  WHERE predicted_offset_f > 0
    AND total_pop >= 1000
    AND (NOT @unmeasured_only OR unmeasured)
),
scored AS (
  SELECT
    point_id,
    ROUND(lat, 5) AS lat,
    ROUND(lon, 5) AS lon,
    geo_id,
    ROUND(predicted_offset_f, 2) AS predicted_offset_f,
    unmeasured,
    TO_JSON_STRING(drivers) AS drivers_json,
    total_pop,
    pop_65_plus,
    ROUND(share_65_plus, 4) AS share_65_plus,
    car_free_households,
    ROUND(median_age, 1) AS median_age,
    ROUND(poverty_rate, 4) AS poverty_rate,
    ROUND(no_vehicle_rate, 4) AS no_vehicle_rate,
    ROUND(median_income, 0) AS median_income,
    model_version,
    ROUND(
        0.35 * COALESCE(z_hazard, 0)
      + 0.25 * COALESCE(z_novehicle, 0)
      + 0.20 * COALESCE(z_age65, 0)
      + 0.15 * COALESCE(z_poverty, 0)
      + 0.05 * COALESCE(z_pop, 0),
      3
    ) AS priority_score
  FROM z
),
best_per_tract AS (
  SELECT *
  FROM scored
  QUALIFY ROW_NUMBER() OVER (PARTITION BY geo_id ORDER BY priority_score DESC, unmeasured DESC, point_id) = 1
)
SELECT *
FROM best_per_tract
ORDER BY priority_score DESC, point_id
LIMIT @limit
