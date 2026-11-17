-- a4i_grid.blockgroup_exposure
-- IMPACT LAYER source. One row per NYC census block group (2010 boundaries), ~6,500 rows.
-- Block groups are ~3x finer than tracts (Brooklyn: 2,085 vs 761).
--
-- Source: ACS 2018 5-year, the newest ACS block-group table in BigQuery. All 2,085 Brooklyn
-- block groups join to the geometry table.
-- Block-group ACS has NO car-ownership or poverty columns; those stay at tract level
-- (a4i_grid.tract_exposure) and cell_impact labels them as tract values.
--
-- Race/ethnicity deliberately not selected. Never a model input; demographics as a whole
-- are for ranking and the equity audit only.

CREATE OR REPLACE TABLE a4i_grid.blockgroup_exposure AS
WITH acs AS (
  SELECT
    LPAD(geo_id, 12, '0') AS bg_geo_id,
    IF(total_pop < 0, NULL, total_pop)                 AS total_pop,
    IF(median_age < 0, NULL, median_age)               AS median_age,
    IF(median_income < 0, NULL, median_income)         AS median_income,
    IF(income_per_capita < 0, NULL, income_per_capita) AS income_per_capita,
    IF(households < 0, NULL, households)               AS households,
    IF(housing_units < 0, NULL, housing_units)         AS housing_units,
    IF(housing_units_renter_occupied < 0, NULL, housing_units_renter_occupied) AS renter_households,
    IF(rent_over_50_percent < 0, NULL, rent_over_50_percent)                   AS renters_rent_over_50pct,
    male_65_to_66 + male_67_to_69 + male_70_to_74 + male_75_to_79 + male_80_to_84
      + male_85_and_over + female_65_to_66 + female_67_to_69 + female_70_to_74
      + female_75_to_79 + female_80_to_84 + female_85_and_over AS pop_65_plus
  FROM `bigquery-public-data.census_bureau_acs.blockgroup_2018_5yr`
)
SELECT
  g.geo_id                                        AS bg_geo_id,
  SUBSTR(g.geo_id, 1, 11)                         AS tract_geo_id,
  g.county_fips_code                              AS county_fips,
  g.area_land_meters                              AS area_land_m2,
  g.area_water_meters                             AS area_water_m2,
  a.total_pop,
  IF(a.pop_65_plus < 0, NULL, a.pop_65_plus)      AS pop_65_plus,
  IF(a.total_pop > 0 AND a.pop_65_plus >= 0, a.pop_65_plus / a.total_pop, NULL) AS share_65_plus,
  a.median_age,
  a.median_income,
  a.income_per_capita,
  a.households,
  a.housing_units,
  a.renter_households,
  IF(a.households > 0, a.renter_households / a.households, NULL)                AS renter_share,
  -- severe rent burden: renters paying > 50% of income on rent (can't afford to run AC)
  IF(a.renter_households > 0, a.renters_rent_over_50pct / a.renter_households, NULL)
                                                  AS severe_rent_burden_rate,
  SAFE_DIVIDE(a.total_pop, g.area_land_meters / 1e6) AS pop_per_km2,
  g.blockgroup_geom                               AS bg_geom
FROM `bigquery-public-data.geo_census_blockgroups.blockgroups_36` g
LEFT JOIN acs a ON a.bg_geo_id = g.geo_id
WHERE g.county_fips_code IN ('005', '047', '061', '081', '085');   -- the five NYC boroughs
