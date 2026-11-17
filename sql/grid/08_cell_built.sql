-- a4i_grid.cell_built
-- BUILT-ENVIRONMENT LAYER. One row per cell. These are the BigQuery ML model features:
-- only things computable for a cell no car drove through.
--
--   tract_water_share            share of the cell's tract that is water (waterfront proxy)
--   bg_housing_units_per_km2     built density of the cell's block group
--   dist_open_space_m            distance to the nearest large, near-empty tract (pop < 200,
--                                land > 0.3 km2): parks, cemeteries, Floyd Bennett Field.
--                                A proxy that mixes green and paved open land.
--   trees_50m/100m/250m, tree_dbh_sum_100m   live street trees (2015 census) near the centre
--
-- EPA Smart Location Database: NOT loaded yet. When it is, join it on bg_geo_id
-- (EPA's GEOID10 is the same 12-character 2010 block-group ID) and add its columns here.
--
-- Known gap: distance to shoreline (no usable harbor/East River shoreline in BigQuery).

CREATE OR REPLACE TABLE a4i_grid.cell_built
CLUSTER BY cell_i, cell_j AS
WITH
trees AS (
  SELECT ST_GEOGPOINT(longitude, latitude) AS g, tree_dbh
  FROM nyc_trees.tree_census_2015
  WHERE status = 'Alive'
),
tree_feats AS (
  SELECT
    c.cell_i, c.cell_j,
    COUNTIF(ST_DWITHIN(c.center, t.g, 50))                 AS trees_50m,
    COUNTIF(ST_DWITHIN(c.center, t.g, 100))                AS trees_100m,
    COUNT(*)                                               AS trees_250m,
    SUM(IF(ST_DWITHIN(c.center, t.g, 100), t.tree_dbh, 0)) AS tree_dbh_sum_100m
  FROM a4i_grid.cells c
  JOIN trees t ON ST_DWITHIN(c.center, t.g, 250)
  GROUP BY 1, 2
),
open_space AS (
  SELECT ST_UNION_AGG(tract_geom) AS geom
  FROM a4i_grid.tract_exposure
  WHERE total_pop < 200 AND area_land_m2 > 300000
)
SELECT
  c.cell_i,
  c.cell_j,
  t.water_share                        AS tract_water_share,
  bg.housing_units / NULLIF(bg.area_land_m2 / 1e6, 0) AS bg_housing_units_per_km2,
  ST_DISTANCE(c.center, os.geom)       AS dist_open_space_m,
  IFNULL(tf.trees_50m, 0)              AS trees_50m,
  IFNULL(tf.trees_100m, 0)             AS trees_100m,
  IFNULL(tf.trees_250m, 0)             AS trees_250m,
  IFNULL(tf.tree_dbh_sum_100m, 0)      AS tree_dbh_sum_100m
FROM a4i_grid.cells c
CROSS JOIN open_space os
LEFT JOIN tree_feats tf USING (cell_i, cell_j)
LEFT JOIN a4i_grid.tract_exposure t       ON t.geo_id     = c.tract_geo_id
LEFT JOIN a4i_grid.blockgroup_exposure bg ON bg.bg_geo_id = c.bg_geo_id;
