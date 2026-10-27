-- audit.sql: recommended-site tracts vs. the whole city, population-weighted.
-- Params : @site_geo_ids ARRAY<STRING>
-- Owner  : data lane (SQL) / agent lane (run_equity_audit tool)
-- NOTE   : output check only. Nothing here feeds back into the model.
WITH t AS (
  SELECT geo_id, total_pop, median_income, poverty_rate, no_vehicle_rate, median_age,
         NTILE(5) OVER (ORDER BY poverty_rate) = 5 AS top_poverty_quintile
  FROM `PROJECT.a4i_climate.tract_demographics`
  WHERE total_pop > 0
),
agg AS (
  SELECT
    grp,
    SAFE_DIVIDE(SUM(total_pop * median_income),   SUM(IF(median_income   IS NULL, 0, total_pop))) AS median_income,
    SAFE_DIVIDE(SUM(total_pop * poverty_rate),    SUM(IF(poverty_rate    IS NULL, 0, total_pop))) AS poverty_rate,
    SAFE_DIVIDE(SUM(total_pop * no_vehicle_rate), SUM(IF(no_vehicle_rate IS NULL, 0, total_pop))) AS no_vehicle_rate,
    SAFE_DIVIDE(SUM(total_pop * median_age),      SUM(IF(median_age      IS NULL, 0, total_pop))) AS median_age,
    SAFE_DIVIDE(SUM(IF(top_poverty_quintile, total_pop, 0)), SUM(total_pop))                      AS share_in_top_poverty_quintile,
    SUM(total_pop) AS people,
    COUNT(*) AS tracts
  FROM (
    SELECT 'city' AS grp, * FROM t
    UNION ALL
    SELECT 'sites' AS grp, * FROM t WHERE geo_id IN UNNEST(@site_geo_ids)
  )
  GROUP BY grp
)
SELECT
  metric,
  ROUND(MAX(IF(grp = 'sites', v, NULL)), 3) AS sites_value,
  ROUND(MAX(IF(grp = 'city',  v, NULL)), 3) AS city_value,
  ROUND(SAFE_DIVIDE(MAX(IF(grp = 'sites', v, NULL)), MAX(IF(grp = 'city', v, NULL))), 2) AS ratio
FROM agg,
UNNEST([
  STRUCT('median_income' AS metric, median_income AS v),
  ('poverty_rate', poverty_rate),
  ('no_vehicle_rate', no_vehicle_rate),
  ('median_age', median_age),
  ('share_in_top_poverty_quintile', share_in_top_poverty_quintile),
  ('people', CAST(people AS FLOAT64)),
  ('tracts', CAST(tracts AS FLOAT64))
])
GROUP BY metric
ORDER BY metric;
