-- sql/audit/audit.sql: Post-hoc equity audit comparing recommended cooling-center tracts vs. Atlanta citywide baseline.
-- Reads: `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`, `bigquery-public-data.census_bureau_acs.censustract_2020_5yr`
-- NOTE : Output check only. Race/ethnicity is strictly excluded from model training and site ranking.
WITH t AS (
  SELECT
    tr.geo_id,
    tr.total_pop,
    tr.pop_65_plus,
    tr.share_65_plus,
    tr.no_cars AS car_free_households,
    tr.median_income,
    tr.poverty_rate,
    tr.no_vehicle_rate,
    tr.median_age,
    NTILE(5) OVER (ORDER BY tr.poverty_rate) = 5 AS top_poverty_quintile,
    SAFE_DIVIDE(acs.black_pop, acs.total_pop) AS black_share,
    SAFE_DIVIDE(acs.white_pop, acs.total_pop) AS white_share
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts` tr
  LEFT JOIN `bigquery-public-data.census_bureau_acs.censustract_2020_5yr` acs
    ON LPAD(CAST(acs.geo_id AS STRING), 11, '0') = tr.geo_id
  WHERE tr.total_pop > 0
),
agg AS (
  SELECT
    grp,
    SAFE_DIVIDE(SUM(total_pop * median_income),   SUM(IF(median_income   IS NULL, 0, total_pop))) AS median_income,
    SAFE_DIVIDE(SUM(total_pop * poverty_rate),    SUM(IF(poverty_rate    IS NULL, 0, total_pop))) AS poverty_rate,
    SAFE_DIVIDE(SUM(total_pop * no_vehicle_rate), SUM(IF(no_vehicle_rate IS NULL, 0, total_pop))) AS no_vehicle_rate,
    SAFE_DIVIDE(SUM(pop_65_plus),                 SUM(total_pop))                                 AS share_65_plus,
    SAFE_DIVIDE(SUM(total_pop * median_age),      SUM(IF(median_age      IS NULL, 0, total_pop))) AS median_age,
    SAFE_DIVIDE(SUM(IF(top_poverty_quintile, total_pop, 0)), SUM(total_pop))                      AS share_in_top_poverty_quintile,
    SAFE_DIVIDE(SUM(total_pop * black_share),     SUM(total_pop))                                 AS posthoc_black_share,
    SAFE_DIVIDE(SUM(total_pop * white_share),     SUM(total_pop))                                 AS posthoc_white_share,
    SUM(total_pop) AS people,
    SUM(pop_65_plus) AS seniors_65_plus,
    SUM(car_free_households) AS car_free_hh
  FROM (
    SELECT 'city' AS grp, * FROM t
    UNION ALL
    SELECT 'sites' AS grp, * FROM t WHERE geo_id IN ('13121007603', '13121004200', '13121004800')
  )
  GROUP BY grp
)
SELECT
  metric,
  ROUND(MAX(IF(grp = 'sites', v, NULL)), 4) AS sites_value,
  ROUND(MAX(IF(grp = 'city',  v, NULL)), 4) AS city_value,
  ROUND(SAFE_DIVIDE(MAX(IF(grp = 'sites', v, NULL)), MAX(IF(grp = 'city', v, NULL))), 2) AS ratio
FROM agg,
UNNEST([
  STRUCT('1_poverty_rate' AS metric, poverty_rate AS v),
  ('2_no_vehicle_rate', no_vehicle_rate),
  ('3_share_65_plus', share_65_plus),
  ('4_median_income_usd', median_income),
  ('5_median_age_years', median_age),
  ('6_share_in_top_poverty_quintile', share_in_top_poverty_quintile),
  ('7_posthoc_black_resident_share', posthoc_black_share),
  ('8_posthoc_white_resident_share', posthoc_white_share),
  ('9_people_in_tracts', CAST(people AS FLOAT64)),
  ('9b_seniors_65_plus_in_tracts', CAST(seniors_65_plus AS FLOAT64)),
  ('9c_car_free_hh_in_tracts', CAST(car_free_hh AS FLOAT64))
])
GROUP BY metric
ORDER BY metric;
