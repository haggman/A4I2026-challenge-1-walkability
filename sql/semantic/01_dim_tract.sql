-- sql/semantic/01_dim_tract.sql
-- Purpose : Business-named, agent- and deck-facing census tract dimension view for Atlanta.
-- Inputs  : `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`
-- Outputs : `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.dim_tract`
-- Owner   : data lane
-- Why     : Provides clean business column names with explicit units and column descriptions for MCP Toolbox,
--           site ranking, and the pitch deck. Strictly excludes race/ethnicity and drive-day measurements.
--
-- Example query:
--   SELECT geo_id, population, pop_65_plus, ROUND(share_65_plus, 3) AS share_65_plus,
--          car_free_households, ROUND(poverty_rate, 3) AS poverty_rate, median_income
--   FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.dim_tract`
--   ORDER BY car_free_households DESC
--   LIMIT 10;

CREATE OR REPLACE VIEW `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.dim_tract`
(
  geo_id OPTIONS (description = '11-character FIPS census tract identifier (string).'),
  centroid_lat OPTIONS (description = 'Tract internal-point centroid latitude (degrees North, WGS84).'),
  centroid_lon OPTIONS (description = 'Tract internal-point centroid longitude (degrees East, WGS84).'),
  population OPTIONS (description = 'Total resident population in the tract (persons, ACS 2020 5-yr).'),
  pop_65_plus OPTIONS (description = 'Residents aged 65 years and older (persons, ACS 2020 5-yr).'),
  share_65_plus OPTIONS (description = 'Share of tract population aged 65 years and older (share 0-1).'),
  car_free_households OPTIONS (description = 'Occupied households with zero vehicles available (households).'),
  households OPTIONS (description = 'Total occupied households in the tract (households).'),
  housing_units OPTIONS (description = 'Total housing units in the tract (housing units).'),
  no_vehicle_rate OPTIONS (description = 'Share of occupied households with no vehicle available (share 0-1).'),
  poverty_rate OPTIONS (description = 'Share of tract population below the federal poverty level (share 0-1).'),
  median_income OPTIONS (description = 'Median household income in the past 12 months (USD, sentinel-cleaned).'),
  median_age OPTIONS (description = 'Median resident age (years, sentinel-cleaned).'),
  median_year_built OPTIONS (description = 'Median year residential structures were built (calendar year 1900-2025).'),
  land_area_km2 OPTIONS (description = 'Tract land area (square kilometers, km2).'),
  pop_density_km2 OPTIONS (description = 'Population density per square kilometer of land (persons per km2).'),
  housing_density_km2 OPTIONS (description = 'Housing unit density per square kilometer of land (housing units per km2).'),
  water_share OPTIONS (description = 'Share of total tract area covered by water (share 0-1).')
)
OPTIONS (
  description = 'Business-named census tract dimension view for Atlanta (353 tracts): population, 65+ seniors, car-free households, income, poverty, age, and built-environment densities. Free of race/ethnicity columns.',
  labels = [('app', 'heat-planner'), ('lane', 'data'), ('layer', 'semantic')]
) AS
SELECT
  geo_id,
  tract_lat AS centroid_lat,
  tract_lon AS centroid_lon,
  total_pop AS population,
  pop_65_plus,
  share_65_plus,
  no_cars AS car_free_households,
  households,
  housing_units,
  no_vehicle_rate,
  poverty_rate,
  median_income,
  median_age,
  median_year_structure_built AS median_year_built,
  land_area_km2,
  pop_density_km2,
  housing_density_km2,
  water_share
FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`;
