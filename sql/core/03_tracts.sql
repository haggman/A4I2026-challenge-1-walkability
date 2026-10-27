-- sql/core/03_tracts.sql
-- Purpose : Build cleaned, sentinel-free census tract table enriched with 65+ population (ACS 2020 5-yr)
--           and land/water area & physical densities (US Census TIGER national tracts).
-- Inputs  : `qwiklabs-gcp-04-ec3596addc43.a4i_climate.tract_demographics`,
--           `bigquery-public-data.census_bureau_acs.censustract_2020_5yr`,
--           `bigquery-public-data.geo_census_tracts.us_census_tracts_national`
-- Outputs : `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`
-- Owner   : data lane
-- Why     : Raw tract_demographics contains Census sentinel -666666666 in median_age (3 rows),
--           median_income (4 rows, 2 with total_pop > 0), and median_year_structure_built (7 rows + 4 zeros).
--           Leaving -666666666 in place corrupts population-weighted city averages in the equity audit and
--           model housing-age features. We strip sentinels to NULL, LPAD geo_id to 11 chars, join the 12
--           ACS 65+ age brackets (pop_65_plus, share_65_plus), and join TIGER land/water areas to compute
--           pop_density_km2, housing_density_km2, and water_share. No race/ethnicity columns are selected.
--
-- Two-number join check (verified):
--   Tracts before joins: 353 | Matched ACS 2020 5-yr: 353 (100%) | Matched TIGER geometry: 353 (100%)

CREATE OR REPLACE TABLE `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`
OPTIONS (
  description = 'Cleaned Atlanta-region census tracts (one row per 11-char geo_id) enriched with ACS 2020 5-yr 65+ population and TIGER land/water area densities. Free of race/ethnicity columns and -666666666 sentinels.',
  labels = [('app', 'heat-planner'), ('lane', 'data'), ('layer', 'core')]
) AS
WITH base AS (
  SELECT
    LPAD(TRIM(CAST(geo_id AS STRING)), 11, '0') AS geo_id,
    SAFE_CAST(tract_lat AS FLOAT64) AS tract_lat,
    SAFE_CAST(tract_lon AS FLOAT64) AS tract_lon,
    ST_GEOGPOINT(SAFE_CAST(tract_lon AS FLOAT64), SAFE_CAST(tract_lat AS FLOAT64)) AS tract_centroid_geog,
    IF(SAFE_CAST(total_pop AS FLOAT64) >= 0, SAFE_CAST(total_pop AS FLOAT64), NULL) AS total_pop,
    IF(SAFE_CAST(households AS FLOAT64) >= 0, SAFE_CAST(households AS FLOAT64), NULL) AS households,
    IF(SAFE_CAST(housing_units AS FLOAT64) >= 0, SAFE_CAST(housing_units AS FLOAT64), NULL) AS housing_units,
    IF(SAFE_CAST(no_cars AS FLOAT64) >= 0, SAFE_CAST(no_cars AS FLOAT64), NULL) AS no_cars,
    IF(SAFE_CAST(no_vehicle_rate AS FLOAT64) BETWEEN 0 AND 1, SAFE_CAST(no_vehicle_rate AS FLOAT64), NULL) AS no_vehicle_rate,
    IF(SAFE_CAST(poverty_rate AS FLOAT64) BETWEEN 0 AND 1, SAFE_CAST(poverty_rate AS FLOAT64), NULL) AS poverty_rate,
    IF(SAFE_CAST(median_age AS FLOAT64) > 0 AND SAFE_CAST(median_age AS FLOAT64) <= 120,
       SAFE_CAST(median_age AS FLOAT64), NULL) AS median_age,
    IF(SAFE_CAST(median_income AS FLOAT64) > 0,
       SAFE_CAST(median_income AS FLOAT64), NULL) AS median_income,
    IF(SAFE_CAST(median_year_structure_built AS FLOAT64) BETWEEN 1900 AND 2025,
       SAFE_CAST(median_year_structure_built AS FLOAT64), NULL) AS median_year_structure_built
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_climate.tract_demographics`
  WHERE geo_id IS NOT NULL
),
acs_65 AS (
  SELECT
    LPAD(TRIM(CAST(geo_id AS STRING)), 11, '0') AS geo_id,
    (COALESCE(SAFE_CAST(male_65_to_66 AS FLOAT64), 0) +
     COALESCE(SAFE_CAST(male_67_to_69 AS FLOAT64), 0) +
     COALESCE(SAFE_CAST(male_70_to_74 AS FLOAT64), 0) +
     COALESCE(SAFE_CAST(male_75_to_79 AS FLOAT64), 0) +
     COALESCE(SAFE_CAST(male_80_to_84 AS FLOAT64), 0) +
     COALESCE(SAFE_CAST(male_85_and_over AS FLOAT64), 0) +
     COALESCE(SAFE_CAST(female_65_to_66 AS FLOAT64), 0) +
     COALESCE(SAFE_CAST(female_67_to_69 AS FLOAT64), 0) +
     COALESCE(SAFE_CAST(female_70_to_74 AS FLOAT64), 0) +
     COALESCE(SAFE_CAST(female_75_to_79 AS FLOAT64), 0) +
     COALESCE(SAFE_CAST(female_80_to_84 AS FLOAT64), 0) +
     COALESCE(SAFE_CAST(female_85_and_over AS FLOAT64), 0)) AS pop_65_plus
  FROM `bigquery-public-data.census_bureau_acs.censustract_2020_5yr`
),
geo AS (
  SELECT
    LPAD(TRIM(CAST(geo_id AS STRING)), 11, '0') AS geo_id,
    SAFE_CAST(area_land_meters AS FLOAT64) AS area_land_m2,
    SAFE_CAST(area_water_meters AS FLOAT64) AS area_water_m2
  FROM `bigquery-public-data.geo_census_tracts.us_census_tracts_national`
)
SELECT
  b.geo_id,
  b.tract_lat,
  b.tract_lon,
  b.tract_centroid_geog,
  b.total_pop,
  a.pop_65_plus,
  SAFE_DIVIDE(a.pop_65_plus, NULLIF(b.total_pop, 0)) AS share_65_plus,
  b.households,
  b.housing_units,
  b.no_cars,
  b.no_vehicle_rate,
  b.poverty_rate,
  b.median_age,
  b.median_income,
  b.median_year_structure_built,
  g.area_land_m2,
  g.area_water_m2,
  g.area_land_m2 / 1e6 AS land_area_km2,
  SAFE_DIVIDE(b.total_pop, NULLIF(g.area_land_m2 / 1e6, 0)) AS pop_density_km2,
  SAFE_DIVIDE(b.housing_units, NULLIF(g.area_land_m2 / 1e6, 0)) AS housing_density_km2,
  SAFE_DIVIDE(g.area_water_m2, NULLIF(g.area_land_m2 + g.area_water_m2, 0)) AS water_share
FROM base b
LEFT JOIN acs_65 a USING (geo_id)
LEFT JOIN geo g USING (geo_id);

ALTER TABLE `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`
  ALTER COLUMN geo_id SET OPTIONS (description = '11-character FIPS census tract identifier (string, LPAD(geo_id, 11, 0)).'),
  ALTER COLUMN tract_lat SET OPTIONS (description = 'Tract internal-point latitude (degrees North, WGS84).'),
  ALTER COLUMN tract_lon SET OPTIONS (description = 'Tract internal-point longitude (degrees East, WGS84).'),
  ALTER COLUMN tract_centroid_geog SET OPTIONS (description = 'Tract internal-point geography (GEOGRAPHY, ST_GEOGPOINT(tract_lon, tract_lat)).'),
  ALTER COLUMN total_pop SET OPTIONS (description = 'Total resident population in tract (persons, ACS 2020 5-yr).'),
  ALTER COLUMN pop_65_plus SET OPTIONS (description = 'Residents aged 65 years and older (persons, sum of 12 ACS male/female 65+ brackets).'),
  ALTER COLUMN share_65_plus SET OPTIONS (description = 'Share of tract population aged 65+ (share 0-1, NULL when total_pop=0).'),
  ALTER COLUMN households SET OPTIONS (description = 'Occupied housing units / households in tract (households).'),
  ALTER COLUMN housing_units SET OPTIONS (description = 'Total housing units in tract (units).'),
  ALTER COLUMN no_cars SET OPTIONS (description = 'Car-free households: occupied housing units with zero vehicles available (households).'),
  ALTER COLUMN no_vehicle_rate SET OPTIONS (description = 'Share of households with no vehicle available (share 0-1).'),
  ALTER COLUMN poverty_rate SET OPTIONS (description = 'Share of population with income below the federal poverty level (share 0-1).'),
  ALTER COLUMN median_age SET OPTIONS (description = 'Median age of tract residents (years; ACS -666666666 sentinel cleaned to NULL).'),
  ALTER COLUMN median_income SET OPTIONS (description = 'Median household income in past 12 months (USD; ACS -666666666 sentinel cleaned to NULL).'),
  ALTER COLUMN median_year_structure_built SET OPTIONS (description = 'Median year residential structures were built (calendar year 1900-2025; sentinels/zeros cleaned to NULL).'),
  ALTER COLUMN area_land_m2 SET OPTIONS (description = 'Tract land area (square meters, US Census TIGER).'),
  ALTER COLUMN area_water_m2 SET OPTIONS (description = 'Tract water area (square meters, US Census TIGER).'),
  ALTER COLUMN land_area_km2 SET OPTIONS (description = 'Tract land area (km2).'),
  ALTER COLUMN pop_density_km2 SET OPTIONS (description = 'Population density per square kilometer of land (persons per km2).'),
  ALTER COLUMN housing_density_km2 SET OPTIONS (description = 'Housing unit density per square kilometer of land (housing units per km2).'),
  ALTER COLUMN water_share SET OPTIONS (description = 'Share of total tract area covered by water (share 0-1).');
