-- a4i_grid.tract_exposure
-- One row per NYC census tract (2020 boundaries): who lives there, cleaned.
-- Used for ranking and the equity audit -- NOT as model inputs.
--
-- Cleaning decisions:
--   * ACS 2019 5-year. The geometry table uses 2010 tract boundaries, and the 2019
--     5-year is the newest ACS on those boundaries: every Brooklyn tract matches.
--     (The 2020 5-year uses 2020 tracts -- 83 Brooklyn tracts don't join -- and its
--     median_income is NULL everywhere.)
--   * median_year_structure_built is dropped: NULL for every tract in 2019, and
--     mostly 0 in 2020.
--   * Census "not available" sentinels (e.g. -666666666) become NULL.
--   * Rates are NULL when the denominator is 0, so empty tracts (parks,
--     cemeteries, airfields) don't show up as 0% poverty.
--   * pop_65_plus sums the 12 ACS age columns (65-66 through 85+, both sexes).
--     In the 2019 table female_65_to_66 is NULL for every tract, so it is ESTIMATED as
--     male_65_to_66 x (female_67_to_69 / male_67_to_69) for the same tract. That one
--     bracket is ~6% of the 65+ total, so the estimate moves the total only slightly.
--   * In the 2019 table `households` is NULL everywhere. occupied_housing_units is the
--     same quantity (no_cars + one..four_more_cars sums to it exactly), so it is the
--     denominator for no_vehicle_rate. no_cars = households with no vehicle.
--   * Race/ethnicity are deliberately not selected.

CREATE OR REPLACE TABLE a4i_grid.tract_exposure AS
WITH acs AS (
  SELECT
    LPAD(geo_id, 11, '0') AS geo_id,
    IF(total_pop < 0, NULL, total_pop)                                   AS total_pop,
    IF(median_age < 0, NULL, median_age)                                 AS median_age,
    IF(median_income < 0, NULL, median_income)                           AS median_income,
    IF(income_per_capita < 0, NULL, income_per_capita)                   AS income_per_capita,
    IF(housing_units < 0, NULL, housing_units)                           AS housing_units,
    IF(occupied_housing_units < 0, NULL, occupied_housing_units)         AS households,
    IF(no_cars < 0, NULL, no_cars)                                       AS no_cars,
    IF(poverty < 0, NULL, poverty)                                       AS poverty,
    IF(pop_determined_poverty_status <= 0, NULL, pop_determined_poverty_status)
                                                                         AS pop_poverty_universe,
    male_65_to_66 + male_67_to_69 + male_70_to_74 + male_75_to_79 + male_80_to_84 + male_85_and_over
      + IFNULL(female_65_to_66,
               male_65_to_66 * IFNULL(SAFE_DIVIDE(female_67_to_69, male_67_to_69), 1.0))
      + female_67_to_69 + female_70_to_74 + female_75_to_79 + female_80_to_84
      + female_85_and_over                                               AS pop_65_plus
  FROM `bigquery-public-data.census_bureau_acs.censustract_2019_5yr`
)
SELECT
  g.geo_id,
  g.county_fips_code                                   AS county_fips,
  CASE g.county_fips_code
    WHEN '047' THEN 'Brooklyn'  WHEN '061' THEN 'Manhattan' WHEN '081' THEN 'Queens'
    WHEN '005' THEN 'Bronx'     WHEN '085' THEN 'Staten Island' END AS borough,
  g.tract_name,
  g.area_land_meters                                   AS area_land_m2,
  g.area_water_meters                                  AS area_water_m2,
  SAFE_DIVIDE(g.area_water_meters, g.area_land_meters + g.area_water_meters) AS water_share,
  a.total_pop,
  IF(a.pop_65_plus < 0, NULL, a.pop_65_plus)           AS pop_65_plus,
  IF(a.total_pop > 0 AND a.pop_65_plus >= 0, a.pop_65_plus / a.total_pop, NULL) AS share_65_plus,
  a.median_age,
  a.median_income,
  a.income_per_capita,
  IF(a.total_pop > 0, SAFE_DIVIDE(a.poverty, a.pop_poverty_universe), NULL)     AS poverty_rate,
  a.households,
  a.no_cars,
  IF(a.households > 0, a.no_cars / a.households, NULL)  AS no_vehicle_rate,
  a.housing_units,
  SAFE_DIVIDE(a.housing_units, g.area_land_meters / 1e6) AS housing_units_per_km2,
  SAFE_DIVIDE(a.total_pop,     g.area_land_meters / 1e6) AS pop_per_km2,
  g.tract_geom
FROM `bigquery-public-data.geo_census_tracts.census_tracts_new_york` g
LEFT JOIN acs a USING (geo_id)
WHERE g.county_fips_code IN ('005', '047', '061', '081', '085');   -- the five NYC boroughs
