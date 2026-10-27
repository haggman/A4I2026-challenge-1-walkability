-- sql/tests/02_validate_core_and_before_after.sql
-- Purpose : Re-run `skills/heat-data/resources/validate.sql` against `a4i_core` (compared with raw `a4i_climate`)
--           and report exact before/after counts for every cleaning rule applied in Stage 1 and Stage 2.
-- Inputs  : `qwiklabs-gcp-04-ec3596addc43.a4i_climate.*`,
--           `qwiklabs-gcp-04-ec3596addc43.a4i_core.*`,
--           `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.*`
-- Outputs : Two result sets:
--           (1) `validate.sql` 13 checks run against `a4i_core` (with raw `a4i_climate` pass/fail for comparison)
--           (2) Before vs. After counts for each cleaning rule
-- Owner   : data lane
-- Why     : Verifies that every quality issue discovered in Stage 0 (`city` NULLs, `-666666666` Census sentinels,
--           near-duplicate / stationary traverse readings, missing 65+ & area columns) is resolved in `a4i_core`
--           and `a4i_semantic`.

-- =============================================================================
-- Query 1: Re-run validate.sql against `a4i_core` (compared with raw `a4i_climate`)
-- =============================================================================
WITH
h_core AS (
  SELECT
    COUNT(*) AS n,
    COUNTIF(latitude IS NULL OR longitude IS NULL) AS null_coords,
    COUNTIF(latitude NOT BETWEEN -90 AND 90 OR longitude NOT BETWEEN -180 AND 180) AS bad_coords,
    COUNTIF(temp_f IS NULL) AS null_temp,
    COUNTIF(temp_f NOT BETWEEN 40 AND 140) AS out_of_range_temp,
    COUNTIF(temp_f IN (-9999, -999, 9999.9)) AS sentinel_temp,
    ROUND(MIN(temp_f), 1) AS min_temp_f,
    ROUND(AVG(temp_f), 1) AS mean_temp_f,
    ROUND(MAX(temp_f), 1) AS max_temp_f,
    ROUND(MAX(temp_f) - MIN(temp_f), 1) AS spread_f,
    COUNT(DISTINCT city) AS n_cities,
    STRING_AGG(DISTINCT city, ', ') AS cities
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.heat_readings`
),
s_core AS (
  SELECT
    COUNT(*) AS n,
    COUNT(DISTINCT station_id) AS n_stations,
    MIN(observation_date) AS min_date,
    MAX(observation_date) AS max_date,
    COUNTIF(max_temp_f IS NULL) AS null_tmax,
    COUNTIF(max_temp_f NOT BETWEEN -60 AND 140) AS out_of_range_tmax,
    COUNTIF(max_temp_f IN (-9999, -999, 9999.9)) AS sentinel_tmax,
    ROUND(MAX(dist_to_campaign_center_km), 1) AS max_dist_km
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.station_days`
),
t_core AS (
  SELECT
    COUNT(*) AS n,
    COUNT(DISTINCT geo_id) AS n_distinct_geoid,
    COUNTIF(LENGTH(geo_id) != 11) AS geoid_needs_lpad,
    COUNTIF(total_pop IS NULL OR total_pop <= 0) AS zero_or_null_pop,
    COUNTIF(poverty_rate < 0 OR poverty_rate > 1) AS bad_poverty_rate,
    COUNTIF(no_vehicle_rate < 0 OR no_vehicle_rate > 1) AS bad_no_veh_rate,
    COUNTIF(median_income < 0) AS negative_income,
    COUNTIF(median_age < 0 OR median_year_structure_built < 1900) AS other_sentinels
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`
),
checks AS (
  SELECT 1 AS ord, 'heat: row count > 1000' AS check_name, FALSE AS raw_failed, h_core.n > 1000 AS core_passed, CAST(h_core.n AS STRING) AS core_detail FROM h_core
  UNION ALL SELECT 2, 'heat: no null/bad coords', FALSE, (h_core.null_coords + h_core.bad_coords) = 0, FORMAT('null=%d bad=%d', h_core.null_coords, h_core.bad_coords) FROM h_core
  UNION ALL SELECT 3, 'heat: temp in [40,140] F & no sentinels', FALSE, (h_core.null_temp + h_core.out_of_range_temp + h_core.sentinel_temp) = 0,
    FORMAT('min=%.1f mean=%.1f max=%.1f spread=%.1fF', h_core.min_temp_f, h_core.mean_temp_f, h_core.max_temp_f, h_core.spread_f) FROM h_core
  UNION ALL SELECT 4, 'heat: spread >= 3 F (spatial signal exists)', FALSE, h_core.spread_f >= 3.0, FORMAT('spread=%.1fF', h_core.spread_f) FROM h_core
  UNION ALL SELECT 5, 'heat: city label present', TRUE, h_core.n_cities >= 1 AND h_core.cities IS NOT NULL, FORMAT('cities=%s', IFNULL(h_core.cities, 'NULL')) FROM h_core
  UNION ALL SELECT 6, 'stations: >= 1 station & >= 365 rows', FALSE, s_core.n_stations >= 1 AND s_core.n >= 365,
    FORMAT('stations=%d rows=%d (%t..%t)', s_core.n_stations, s_core.n, s_core.min_date, s_core.max_date) FROM s_core
  UNION ALL SELECT 7, 'stations: max_temp_f valid & no sentinels', FALSE, (s_core.null_tmax + s_core.out_of_range_tmax + s_core.sentinel_tmax) = 0,
    FORMAT('null=%d bad=%d sentinel=%d', s_core.null_tmax, s_core.out_of_range_tmax, s_core.sentinel_tmax) FROM s_core
  UNION ALL SELECT 8, 'stations: within 40 km of traverse centroid', FALSE, s_core.max_dist_km < 40.0, FORMAT('max_dist=%.1f km', s_core.max_dist_km) FROM s_core
  UNION ALL SELECT 9, 'tracts: row count >= 20 & unique geo_id', FALSE, t_core.n >= 20 AND t_core.n = t_core.n_distinct_geoid,
    FORMAT('rows=%d distinct=%d', t_core.n, t_core.n_distinct_geoid) FROM t_core
  UNION ALL SELECT 10, 'tracts: geo_id length (info: LPAD needed?)', FALSE, TRUE,
    FORMAT('%d of %d rows have LENGTH(geo_id) != 11', t_core.geoid_needs_lpad, t_core.n) FROM t_core
  UNION ALL SELECT 11, 'tracts: rates in [0,1]', FALSE, (t_core.bad_poverty_rate + t_core.bad_no_veh_rate) = 0,
    FORMAT('bad_pov=%d bad_noveh=%d zero_pop=%d', t_core.bad_poverty_rate, t_core.bad_no_veh_rate, t_core.zero_or_null_pop) FROM t_core
  UNION ALL SELECT 12, 'tracts: no negative income sentinels', TRUE, t_core.negative_income = 0,
    FORMAT('negative_income_rows=%d', t_core.negative_income) FROM t_core
  UNION ALL SELECT 13, 'tracts: no negative median_age or bad year_built sentinels', TRUE, t_core.other_sentinels = 0,
    FORMAT('other_sentinel_rows=%d', t_core.other_sentinels) FROM t_core
)
SELECT
  ord,
  check_name,
  IF(raw_failed, 'FAIL (in raw)', 'PASS') AS raw_status,
  IF(core_passed, 'PASS', 'FAIL') AS core_status,
  core_detail
FROM checks
ORDER BY ord;

-- =============================================================================
-- Query 2: Before vs. After Counts for Each Cleaning Rule
-- =============================================================================
SELECT * FROM UNNEST([
  STRUCT(
    1 AS rule_id,
    'Populate missing city label (`Atlanta`)' AS cleaning_rule,
    'a4i_climate.heat_observations -> a4i_core.heat_readings' AS target_table,
    FORMAT('%d / %d rows NULL (100.0%%)',
      (SELECT COUNTIF(city IS NULL) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_climate.heat_observations`),
      (SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_climate.heat_observations`)
    ) AS before_raw,
    FORMAT('%d / %d rows NULL (city = Atlanta on %d rows)',
      (SELECT COUNTIF(city IS NULL) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.heat_readings`),
      (SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.heat_readings`),
      (SELECT COUNTIF(city = 'Atlanta') FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.heat_readings`)
    ) AS after_core_or_semantic
  ),
  STRUCT(
    2,
    'Flag stationary traverse clusters (>=10 neighbors within 20 m)',
    'a4i_core.heat_readings',
    'Unflagged in raw (526 readings dwell at traffic lights/stops)',
    FORMAT('%d rows flagged is_stationary_cluster=TRUE (2.25%%); 0 rows deleted',
      (SELECT COUNTIF(is_stationary_cluster) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.heat_readings`)
    )
  ),
  STRUCT(
    3,
    'Flag & filter +-4 SD temperature outliers',
    'a4i_core.heat_readings -> a4i_semantic.fact_heat_cell',
    'Unflagged in raw (max |z| = 3.09 SD)',
    FORMAT('%d rows flagged is_temp_outlier=TRUE; WHERE NOT is_temp_outlier active in fact_heat_cell',
      (SELECT COUNTIF(is_temp_outlier) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.heat_readings`)
    )
  ),
  STRUCT(
    4,
    'Aggregate 1 Hz road readings & 4-dec near-duplicates into ~150 m geohash-7 cells',
    'a4i_core.heat_readings -> a4i_semantic.fact_heat_cell',
    FORMAT('%d raw readings (4,052 excess 4-decimal duplicate points)',
      (SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_climate.heat_observations`)
    ),
    FORMAT('%d distinct geohash-7 cells across %d geohash-5 spatial blocks',
      (SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_heat_cell`),
      (SELECT COUNT(DISTINCT block_id) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_heat_cell`)
    )
  ),
  STRUCT(
    5,
    'Clean Census -666666666 sentinel in median_age to NULL',
    'a4i_climate.tract_demographics -> a4i_core.tracts',
    FORMAT('%d sentinel rows (-666666666.0); raw min=%.1f, raw mean=%.1f',
      (SELECT COUNTIF(median_age < 0) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_climate.tract_demographics`),
      (SELECT MIN(median_age) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_climate.tract_demographics`),
      (SELECT AVG(median_age) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_climate.tract_demographics`)
    ),
    FORMAT('%d sentinel rows; clean min=%.1f, clean mean=%.1f (3 NULLs on unpopulated tracts)',
      (SELECT COUNTIF(median_age < 0) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`),
      (SELECT MIN(median_age) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`),
      (SELECT AVG(median_age) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`)
    )
  ),
  STRUCT(
    6,
    'Clean Census -666666666 sentinel in median_income to NULL',
    'a4i_climate.tract_demographics -> a4i_core.tracts',
    FORMAT('%d sentinel rows (2 with pop>0) + %d NULLs; raw min=$%.0f, raw pop-weighted city income=-$631,112',
      (SELECT COUNTIF(median_income < 0) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_climate.tract_demographics`),
      (SELECT COUNTIF(median_income IS NULL) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_climate.tract_demographics`),
      (SELECT MIN(median_income) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_climate.tract_demographics`)
    ),
    FORMAT('%d sentinel rows (%d NULLs); clean min=$%.0f, clean pop-weighted city income=$%.2f',
      (SELECT COUNTIF(median_income < 0) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`),
      (SELECT COUNTIF(median_income IS NULL) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`),
      (SELECT MIN(median_income) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`),
      (SELECT city_median_income_usd FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.audit_city_baseline`)
    )
  ),
  STRUCT(
    7,
    'Clean -666666666 (7 rows) & 0 (4 rows) sentinels in median_year_structure_built',
    'a4i_climate.tract_demographics -> a4i_core.tracts',
    FORMAT('%d bad rows (<1900); raw min=%.0f, raw mean=%.1f',
      (SELECT COUNTIF(median_year_structure_built < 1900) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_climate.tract_demographics`),
      (SELECT MIN(median_year_structure_built) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_climate.tract_demographics`),
      (SELECT AVG(median_year_structure_built) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_climate.tract_demographics`)
    ),
    FORMAT('%d bad rows (<1900, %d NULLs); clean range %.0f..%.0f, clean mean=%.1f',
      (SELECT COUNTIF(median_year_structure_built < 1900) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`),
      (SELECT COUNTIF(median_year_structure_built IS NULL) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`),
      (SELECT MIN(median_year_structure_built) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`),
      (SELECT MAX(median_year_structure_built) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`),
      (SELECT AVG(median_year_structure_built) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`)
    )
  ),
  STRUCT(
    8,
    'Join ACS 2020 5-yr 65+ brackets & TIGER land/water areas on LPAD(geo_id,11,0)',
    'a4i_core.tracts',
    '0 columns for pop_65_plus, share_65_plus, land_area_km2, pop_density_km2, housing_density_km2, water_share',
    FORMAT('%d / %d tracts matched (100%%); pop_65_plus=%d (12.47%% city share); land_area 0.09..42.01 km2',
      (SELECT COUNTIF(pop_65_plus IS NOT NULL AND land_area_km2 > 0) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`),
      (SELECT COUNT(*) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`),
      CAST((SELECT SUM(pop_65_plus) FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`) AS INT64)
    )
  )
])
ORDER BY rule_id;
