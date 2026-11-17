-- a4i_grid.cells
-- BASE TABLE. The grid itself: one row per 0.001-degree cell in the study area.
-- Every layer table (cell_heat, cell_built, cell_impact) joins to this on (cell_i, cell_j).
--
-- Study area: every cell whose centre is in Brooklyn (Kings County), plus any cell within
-- 1 km of a driven cell (the campaign also drove lower Manhattan and a strip of Queens).
--
--   is_driven          the cell has a measured offset (in cell_heat)
--   dist_to_driven_m   distance to the nearest driven cell centre (NULL if > 3 km)
--   in_training_range  within 1 km of a driven cell; beyond that a prediction is extrapolation
--   is_land            rough mask: driven, or live street trees within 250 m

CREATE OR REPLACE TABLE a4i_grid.cells
CLUSTER BY cell_i, cell_j AS
WITH
brooklyn AS (
  SELECT ST_UNION_AGG(tract_geom) AS geom
  FROM a4i_grid.tract_exposure
  WHERE county_fips = '047'
),
driven AS (
  SELECT cell_i, cell_j,
         ST_GEOGPOINT((cell_j + 0.5) * 0.001, (cell_i + 0.5) * 0.001) AS center
  FROM a4i_grid.cell_heat
),
bk_box AS (
  SELECT
    CAST(FLOOR(ST_BOUNDINGBOX(geom).ymin / 0.001) AS INT64) AS i0,
    CAST(FLOOR(ST_BOUNDINGBOX(geom).ymax / 0.001) AS INT64) AS i1,
    CAST(FLOOR(ST_BOUNDINGBOX(geom).xmin / 0.001) AS INT64) AS j0,
    CAST(FLOOR(ST_BOUNDINGBOX(geom).xmax / 0.001) AS INT64) AS j1
  FROM brooklyn
),
bounds AS (
  SELECT
    LEAST(ANY_VALUE(b.i0), MIN(d.cell_i)) - 10    AS i0,
    GREATEST(ANY_VALUE(b.i1), MAX(d.cell_i)) + 10 AS i1,
    LEAST(ANY_VALUE(b.j0), MIN(d.cell_j)) - 10    AS j0,
    GREATEST(ANY_VALUE(b.j1), MAX(d.cell_j)) + 10 AS j1
  FROM bk_box b CROSS JOIN driven d
),
candidates AS (
  SELECT i AS cell_i, j AS cell_j,
         ST_GEOGPOINT((j + 0.5) * 0.001, (i + 0.5) * 0.001) AS center
  FROM bounds,
       UNNEST(GENERATE_ARRAY(i0, i1)) AS i,
       UNNEST(GENERATE_ARRAY(j0, j1)) AS j
),
nearest_driven AS (
  SELECT c.cell_i, c.cell_j, MIN(ST_DISTANCE(c.center, d.center)) AS dist_to_driven_m
  FROM candidates c
  JOIN driven d ON ST_DWITHIN(c.center, d.center, 3000)
  GROUP BY 1, 2
),
in_area AS (
  SELECT c.*, nd.dist_to_driven_m
  FROM candidates c
  CROSS JOIN brooklyn b
  LEFT JOIN nearest_driven nd USING (cell_i, cell_j)
  WHERE ST_CONTAINS(b.geom, c.center) OR nd.dist_to_driven_m <= 1000
),
has_trees AS (
  SELECT DISTINCT a.cell_i, a.cell_j
  FROM in_area a
  JOIN nyc_trees.tree_census_2015 t
    ON t.status = 'Alive'
   AND ST_DWITHIN(a.center, ST_GEOGPOINT(t.longitude, t.latitude), 250)
)
SELECT
  a.cell_i,
  a.cell_j,
  ST_Y(a.center)                                   AS lat,
  ST_X(a.center)                                   AS lon,
  a.center,
  bg.bg_geo_id,
  bg.tract_geo_id,
  CASE bg.county_fips
    WHEN '047' THEN 'Brooklyn'  WHEN '061' THEN 'Manhattan' WHEN '081' THEN 'Queens'
    WHEN '005' THEN 'Bronx'     WHEN '085' THEN 'Staten Island' END AS borough,
  h.cell_i IS NOT NULL                             AS is_driven,
  a.dist_to_driven_m,
  IFNULL(a.dist_to_driven_m <= 1000, FALSE)        AS in_training_range,
  (h.cell_i IS NOT NULL OR ht.cell_i IS NOT NULL) AND bg.bg_geo_id IS NOT NULL AS is_land
FROM in_area a
LEFT JOIN a4i_grid.cell_heat h USING (cell_i, cell_j)
LEFT JOIN has_trees ht USING (cell_i, cell_j)
LEFT JOIN a4i_grid.blockgroup_exposure bg ON ST_CONTAINS(bg.bg_geom, a.center);
