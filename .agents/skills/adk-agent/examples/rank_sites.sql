-- rank_sites.sql: score precomputed grid predictions by hazard × vulnerability.
-- Params: @w_hazard, @w_novehicle, @w_age, @w_poverty, @w_pop (FLOAT64), @unmeasured_only (BOOL)
-- Reads : PROJECT.a4i_ml.grid_predictions (built by the data lane's 04_serve.sql)
-- Note  : z-scores are city-relative, so weights are comparable across metrics.
WITH z AS (
  SELECT
    *,
    (predicted_offset_f - AVG(predicted_offset_f) OVER ()) / NULLIF(STDDEV(predicted_offset_f) OVER (), 0) AS z_hazard,
    (no_vehicle_rate - AVG(no_vehicle_rate) OVER ()) / NULLIF(STDDEV(no_vehicle_rate) OVER (), 0)          AS z_novehicle,
    (median_age      - AVG(median_age)      OVER ()) / NULLIF(STDDEV(median_age)      OVER (), 0)          AS z_age,
    (poverty_rate    - AVG(poverty_rate)    OVER ()) / NULLIF(STDDEV(poverty_rate)    OVER (), 0)          AS z_poverty,
    (total_pop       - AVG(total_pop)       OVER ()) / NULLIF(STDDEV(total_pop)       OVER (), 0)          AS z_pop
  FROM `PROJECT.a4i_ml.grid_predictions`
  WHERE predicted_offset_f > 0                     -- only places hotter than average
    AND (NOT @unmeasured_only OR unmeasured)
)
SELECT
  point_id, lat, lon, geo_id, predicted_offset_f,
  ARRAY(SELECT AS STRUCT a.feature, a.attribution AS attribution_f
        FROM UNNEST(drivers) a ORDER BY ABS(a.attribution) DESC) AS drivers,
  total_pop, median_age, poverty_rate, no_vehicle_rate, unmeasured,
    @w_hazard    * COALESCE(z_hazard, 0)
  + @w_novehicle * COALESCE(z_novehicle, 0)
  + @w_age       * COALESCE(z_age, 0)
  + @w_poverty   * COALESCE(z_poverty, 0)
  + @w_pop       * COALESCE(z_pop, 0) AS score
FROM z
ORDER BY score DESC
LIMIT 300;
