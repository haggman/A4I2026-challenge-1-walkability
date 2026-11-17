-- a4i_grid.cell_impact
-- IMPACT LAYER. One row per cell: who lives here and how exposed they are.
-- For ranking, dispatch and the equity audit. NEVER a model input.
--
-- Two geographic levels, named by prefix:
--   bg_*     block group (ACS 2018): population, age, income, rent burden
--   tract_*  tract (ACS 2019): car ownership and poverty, which block-group ACS lacks
--
-- est_* columns spread the block group's people evenly over its land cells:
--   est_residents = bg total_pop / number of land cells in that block group
-- A rough allocation (it ignores where in the block group people actually live), but it
-- lets you add up "people affected" over any set of cells without double counting.

CREATE OR REPLACE TABLE a4i_grid.cell_impact
CLUSTER BY cell_i, cell_j AS
WITH land_cells_per_bg AS (
  SELECT bg_geo_id, COUNT(*) AS n_land_cells
  FROM a4i_grid.cells
  WHERE is_land
  GROUP BY bg_geo_id
)
SELECT
  c.cell_i,
  c.cell_j,
  c.bg_geo_id,
  c.tract_geo_id,
  -- block group
  bg.total_pop                    AS bg_total_pop,
  bg.share_65_plus                AS bg_share_65_plus,
  bg.median_age                   AS bg_median_age,
  bg.median_income                AS bg_median_income,
  bg.income_per_capita            AS bg_income_per_capita,
  bg.renter_share                 AS bg_renter_share,
  bg.severe_rent_burden_rate      AS bg_severe_rent_burden_rate,
  bg.pop_per_km2                  AS bg_pop_per_km2,
  -- tract
  t.no_vehicle_rate               AS tract_no_vehicle_rate,
  t.poverty_rate                  AS tract_poverty_rate,
  -- per-cell allocations (land cells only)
  IF(c.is_land, bg.total_pop   / n.n_land_cells, 0) AS est_residents,
  IF(c.is_land, bg.pop_65_plus / n.n_land_cells, 0) AS est_residents_65_plus,
  IF(c.is_land, bg.households  / n.n_land_cells * t.no_vehicle_rate, 0) AS est_households_no_car
FROM a4i_grid.cells c
LEFT JOIN a4i_grid.blockgroup_exposure bg ON bg.bg_geo_id = c.bg_geo_id
LEFT JOIN a4i_grid.tract_exposure t       ON t.geo_id     = c.tract_geo_id
LEFT JOIN land_cells_per_bg n             ON n.bg_geo_id  = c.bg_geo_id;
