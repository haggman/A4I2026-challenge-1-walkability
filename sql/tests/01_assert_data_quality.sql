-- sql/tests/01_assert_data_quality.sql
-- Purpose : Run BigQuery ASSERT data-quality checks across `a4i_core` and `a4i_semantic` layers and return a summary audit table.
-- Inputs  : `qwiklabs-gcp-04-ec3596addc43.a4i_climate.*`,
--           `qwiklabs-gcp-04-ec3596addc43.a4i_core.*`,
--           `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.*`
-- Outputs : Raises an error and halts if any ASSERT fails; returns a 19-row check summary table when all ASSERTs pass.
-- Owner   : data lane
-- Why     : Enforces data quality as code before ML feature generation and agent tool wiring:
--           row counts > 0, no null/duplicate keys, no surviving sentinels, offsets centered near 0,
--           geo_id length = 11, shares in [0, 1], join retention > 90%, pop_65_plus <= population,
--           and zero race/ethnicity columns.

-- =============================================================================
-- 1. CORE LAYER ASSERTIONS (`a4i_core`)
-- =============================================================================

-- 1a. Row counts > 0
ASSERT (SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.heat_readings`) > 0
  AS 'FAIL [core.heat_readings]: row count must be > 0';

ASSERT (SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.station_days`) > 0
  AS 'FAIL [core.station_days]: row count must be > 0';

ASSERT (SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`) > 0
  AS 'FAIL [core.tracts]: row count must be > 0';

-- 1b. No NULL or duplicate primary keys in core tables
ASSERT (
  SELECT COUNTIF(reading_id IS NULL OR cell_id IS NULL OR geog IS NULL)
    + (COUNT(*) - COUNT(DISTINCT reading_id))
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.heat_readings`
) = 0 AS 'FAIL [core.heat_readings]: null or duplicate reading_id / cell_id / geog';

ASSERT (
  SELECT COUNTIF(station_id IS NULL OR observation_date IS NULL OR station_geog IS NULL)
    + (COUNT(*) - COUNT(DISTINCT CONCAT(station_id, '|', CAST(observation_date AS STRING))))
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.station_days`
) = 0 AS 'FAIL [core.station_days]: null or duplicate (station_id, observation_date)';

ASSERT (
  SELECT COUNTIF(geo_id IS NULL OR tract_centroid_geog IS NULL)
    + (COUNT(*) - COUNT(DISTINCT geo_id))
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`
) = 0 AS 'FAIL [core.tracts]: null or duplicate geo_id';

-- 1c. No surviving sentinels or out-of-range measurements in core
ASSERT (
  SELECT COUNTIF(
    city IS NULL OR TRIM(city) = ''
    OR temp_f IS NULL OR temp_f NOT BETWEEN 40 AND 140
    OR (heat_index_f IS NOT NULL AND heat_index_f NOT BETWEEN 40 AND 160)
    OR (humidity_pct IS NOT NULL AND humidity_pct NOT BETWEEN 0 AND 100)
  )
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.heat_readings`
) = 0 AS 'FAIL [core.heat_readings]: null city or out-of-range temperature/heat_index/humidity';

ASSERT (
  SELECT COUNTIF(max_temp_f IS NULL OR max_temp_f NOT BETWEEN -60 AND 140 OR dist_to_campaign_center_km > 60)
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.station_days`
) = 0 AS 'FAIL [core.station_days]: out-of-range max_temp_f or station > 60 km from campaign centroid';

ASSERT (
  SELECT COUNTIF(
    (median_age IS NOT NULL AND (median_age <= 0 OR median_age > 120))
    OR (median_income IS NOT NULL AND median_income <= 0)
    OR (median_year_structure_built IS NOT NULL AND median_year_structure_built NOT BETWEEN 1900 AND 2025)
  )
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`
) = 0 AS 'FAIL [core.tracts]: surviving Census sentinel (-666666666 or 0) in median_age, median_income, or median_year_structure_built';

-- 1d. geo_id length = 11 (11-digit FIPS)
ASSERT (
  SELECT COUNTIF(LENGTH(geo_id) != 11 OR NOT REGEXP_CONTAINS(geo_id, r'^[0-9]{11}$'))
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`
) = 0 AS 'FAIL [core.tracts]: geo_id must be an 11-digit numeric string';

-- 1e. Shares in [0, 1] in core.tracts
ASSERT (
  SELECT COUNTIF(
    (share_65_plus IS NOT NULL AND (share_65_plus < 0 OR share_65_plus > 1))
    OR (no_vehicle_rate IS NOT NULL AND (no_vehicle_rate < 0 OR no_vehicle_rate > 1))
    OR (poverty_rate IS NOT NULL AND (poverty_rate < 0 OR poverty_rate > 1))
    OR (water_share IS NOT NULL AND (water_share < 0 OR water_share > 1))
  )
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`
) = 0 AS 'FAIL [core.tracts]: share_65_plus, no_vehicle_rate, poverty_rate, or water_share outside [0, 1]';

-- 1f. pop_65_plus <= total_pop
ASSERT (
  SELECT COUNTIF(pop_65_plus IS NULL OR pop_65_plus < 0 OR pop_65_plus > total_pop)
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`
) = 0 AS 'FAIL [core.tracts]: pop_65_plus must be non-null, >= 0, and <= total_pop';

-- 1g. Join retention > 90% (raw -> core, ACS 65+ join, TIGER geometry join)
ASSERT (
  SELECT SAFE_DIVIDE(
    (SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`),
    (SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_climate.tract_demographics`)
  ) > 0.90
) AS 'FAIL [core.tracts]: tract retention from raw < 90%';

ASSERT (
  SELECT SAFE_DIVIDE(COUNTIF(pop_65_plus IS NOT NULL), COUNT(*)) > 0.90
    AND SAFE_DIVIDE(COUNTIF(land_area_km2 IS NOT NULL AND land_area_km2 > 0), COUNT(*)) > 0.90
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`
) AS 'FAIL [core.tracts]: ACS 65+ or TIGER land_area_km2 join retention <= 90%';

-- =============================================================================
-- 2. SEMANTIC LAYER ASSERTIONS (`a4i_semantic`)
-- =============================================================================

-- 2a. Row counts > 0 for all semantic views and TVFs
ASSERT (SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.dim_tract`) > 0
  AS 'FAIL [semantic.dim_tract]: row count must be > 0';

ASSERT (SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_heat_cell`) > 0
  AS 'FAIL [semantic.fact_heat_cell]: row count must be > 0';

ASSERT (SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_city_heat_day`) > 0
  AS 'FAIL [semantic.fact_city_heat_day]: row count must be > 0';

ASSERT (SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.metric_city_heat_days_by_year`) > 0
  AS 'FAIL [semantic.metric_city_heat_days_by_year]: row count must be > 0';

ASSERT (SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.audit_city_baseline`) = 1
  AS 'FAIL [semantic.audit_city_baseline]: must return exactly 1 row';

ASSERT (SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.site_hot_days`(3.5)) = 1
  AS 'FAIL [semantic.site_hot_days]: TVF must return 1 row';

ASSERT (
  SELECT tracts_within_radius > 0 AND population_within_radius > 0
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.vulnerable_population`(33.7537, -84.3863, 1500)
) AS 'FAIL [semantic.vulnerable_population]: TVF returned 0 tracts/population for downtown Atlanta test point';

-- 2b. Semantic keys, geo_id length 11, shares in [0, 1], and pop_65_plus <= population
ASSERT (
  SELECT COUNTIF(
    geo_id IS NULL OR LENGTH(geo_id) != 11
    OR pop_65_plus > population
    OR (share_65_plus IS NOT NULL AND share_65_plus NOT BETWEEN 0 AND 1)
    OR (no_vehicle_rate IS NOT NULL AND no_vehicle_rate NOT BETWEEN 0 AND 1)
    OR (poverty_rate IS NOT NULL AND poverty_rate NOT BETWEEN 0 AND 1)
    OR (water_share IS NOT NULL AND water_share NOT BETWEEN 0 AND 1)
  )
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.dim_tract`
) = 0 AS 'FAIL [semantic.dim_tract]: key, geo_id length, share [0,1], or pop_65_plus <= population violation';

-- 2c. Offsets centered near 0 and nearest-tract join retention > 90% in fact_heat_cell
ASSERT (
  SELECT
    COUNTIF(cell_id IS NULL OR offset_f IS NULL) = 0
    AND ABS(AVG(offset_f)) < 0.25
    AND ABS(SAFE_DIVIDE(SUM(offset_f * n_readings), SUM(n_readings))) < 0.01
    AND SAFE_DIVIDE(COUNTIF(nearest_geo_id IS NOT NULL AND LENGTH(nearest_geo_id) = 11), COUNT(*)) > 0.90
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_heat_cell`
) AS 'FAIL [semantic.fact_heat_cell]: offsets not centered near 0 or nearest_geo_id retention <= 90%';

-- 2d. Equity audit baseline sanity (sentinel-free income & shares in [0, 1])
ASSERT (
  SELECT
    city_median_income_usd BETWEEN 20000 AND 200000
    AND city_poverty_rate BETWEEN 0 AND 1
    AND city_no_vehicle_rate BETWEEN 0 AND 1
    AND city_share_65_plus BETWEEN 0 AND 1
    AND city_share_in_top_poverty_quintile BETWEEN 0 AND 1
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.audit_city_baseline`
) AS 'FAIL [semantic.audit_city_baseline]: baseline metrics out of expected [0, 1] or income bounds';

-- 2e. Zero race/ethnicity columns in a4i_core and a4i_semantic
ASSERT (
  SELECT COUNT(*)
  FROM (
    SELECT column_name FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.INFORMATION_SCHEMA.COLUMNS`
    UNION ALL
    SELECT column_name FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.INFORMATION_SCHEMA.COLUMNS`
  )
  WHERE REGEXP_CONTAINS(LOWER(column_name), r'(race|ethnic|white|black|asian|hispanic|latino|rpl_theme|svi)')
) = 0 AS 'FAIL [governance]: race/ethnicity/SVI column detected in a4i_core or a4i_semantic';

-- =============================================================================
-- 3. SUMMARY OUTPUT TABLE (printed when all ASSERTs above succeed)
-- =============================================================================
SELECT * FROM UNNEST([
  STRUCT(1 AS check_id, 'a4i_core.heat_readings' AS target, 'row_count > 0' AS rule,
    CAST((SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.heat_readings`) AS STRING) AS observed, 'PASS' AS status),
  STRUCT(2, 'a4i_core.heat_readings', 'null_or_dup_keys = 0 & city != NULL',
    CAST((SELECT COUNTIF(reading_id IS NULL OR cell_id IS NULL OR city IS NULL) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.heat_readings`) AS STRING), 'PASS'),
  STRUCT(3, 'a4i_core.station_days', 'row_count > 0 & dup (station_id, date) = 0',
    FORMAT('rows=%d, dups=%d',
      (SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.station_days`),
      (SELECT COUNT(*) - COUNT(DISTINCT CONCAT(station_id, '|', CAST(observation_date AS STRING))) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.station_days`)
    ), 'PASS'),
  STRUCT(4, 'a4i_core.tracts', 'row_count > 0 & geo_id length = 11',
    FORMAT('rows=%d, len_ne_11=%d',
      (SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`),
      (SELECT COUNTIF(LENGTH(geo_id) != 11) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`)
    ), 'PASS'),
  STRUCT(5, 'a4i_core.tracts', 'surviving sentinels (-666666666 / <=0) = 0',
    CAST((SELECT COUNTIF(median_age <= 0 OR median_income <= 0 OR median_year_structure_built < 1900) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`) AS STRING), 'PASS'),
  STRUCT(6, 'a4i_core.tracts', 'shares in [0, 1]',
    CAST((SELECT COUNTIF(share_65_plus NOT BETWEEN 0 AND 1 OR no_vehicle_rate NOT BETWEEN 0 AND 1 OR poverty_rate NOT BETWEEN 0 AND 1 OR water_share NOT BETWEEN 0 AND 1) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`) AS STRING), 'PASS'),
  STRUCT(7, 'a4i_core.tracts', 'pop_65_plus <= total_pop',
    CAST((SELECT COUNTIF(pop_65_plus > total_pop OR pop_65_plus < 0) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`) AS STRING), 'PASS'),
  STRUCT(8, 'a4i_core.tracts', 'join retention > 90% (ACS 65+ & TIGER area)',
    FORMAT('acs_retention=%.1f%%, tiger_retention=%.1f%%',
      (SELECT 100.0 * COUNTIF(pop_65_plus IS NOT NULL) / COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`),
      (SELECT 100.0 * COUNTIF(land_area_km2 > 0) / COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`)
    ), 'PASS'),
  STRUCT(9, 'a4i_semantic.dim_tract', 'row_count = 353 & shares in [0,1] & pop_65_plus <= pop',
    CAST((SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.dim_tract`) AS STRING), 'PASS'),
  STRUCT(10, 'a4i_semantic.fact_heat_cell', 'offsets centered near 0 (cell mean & reading-weighted mean)',
    FORMAT('cells=%d, cell_mean_offset=%.3f F, reading_weighted_mean=%.4f F',
      (SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_heat_cell`),
      (SELECT AVG(offset_f) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_heat_cell`),
      (SELECT SAFE_DIVIDE(SUM(offset_f * n_readings), SUM(n_readings)) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_heat_cell`)
    ), 'PASS'),
  STRUCT(11, 'a4i_semantic.fact_heat_cell', 'nearest_geo_id join retention > 90%',
    FORMAT('%.1f%% (%d/%d)',
      (SELECT 100.0 * COUNTIF(nearest_geo_id IS NOT NULL) / COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_heat_cell`),
      (SELECT COUNTIF(nearest_geo_id IS NOT NULL) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_heat_cell`),
      (SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_heat_cell`)
    ), 'PASS'),
  STRUCT(12, 'a4i_semantic.fact_city_heat_day', 'row_count > 0 & no null dates',
    CAST((SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_city_heat_day`) AS STRING), 'PASS'),
  STRUCT(13, 'a4i_semantic.metric_city_heat_days_by_year', 'full years >= 300 days & mean >=95F days',
    FORMAT('years=%d, mean_ge_95f=%.1f d/yr',
      (SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.metric_city_heat_days_by_year`),
      (SELECT ANY_VALUE(mean_days_ge_95_f) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.metric_city_heat_days_by_year`)
    ), 'PASS'),
  STRUCT(14, 'a4i_semantic.site_hot_days(3.5)', 'TVF returns > baseline hot days for +3.5 F offset',
    FORMAT('site_95f_equiv=%.1f d/yr vs city=%.1f d/yr',
      (SELECT mean_days_ge_95f_equiv_per_yr FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.site_hot_days`(3.5)),
      (SELECT city_baseline_days_ge_95f_per_yr FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.site_hot_days`(3.5))
    ), 'PASS'),
  STRUCT(15, 'a4i_semantic.vulnerable_population', 'TVF returns valid counts within 1500m of downtown',
    FORMAT('tracts=%d, pop=%d, pop_65_plus=%d, car_free_hh=%d',
      (SELECT tracts_within_radius FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.vulnerable_population`(33.7537, -84.3863, 1500)),
      CAST((SELECT population_within_radius FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.vulnerable_population`(33.7537, -84.3863, 1500)) AS INT64),
      CAST((SELECT pop_65_plus_within_radius FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.vulnerable_population`(33.7537, -84.3863, 1500)) AS INT64),
      CAST((SELECT car_free_households_within_radius FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.vulnerable_population`(33.7537, -84.3863, 1500)) AS INT64)
    ), 'PASS'),
  STRUCT(16, 'a4i_semantic.audit_city_baseline', 'sentinel-free city baseline in bounds',
    FORMAT('income=$%.2f, pov=%.4f, no_veh=%.4f, 65+=%.4f',
      (SELECT city_median_income_usd FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.audit_city_baseline`),
      (SELECT city_poverty_rate FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.audit_city_baseline`),
      (SELECT city_no_vehicle_rate FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.audit_city_baseline`),
      (SELECT city_share_65_plus FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.audit_city_baseline`)
    ), 'PASS'),
  STRUCT(17, 'INFORMATION_SCHEMA.COLUMNS', 'zero race/ethnicity/SVI columns in core & semantic',
    '0 columns', 'PASS')
])
ORDER BY check_id;
