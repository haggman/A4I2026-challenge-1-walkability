-- a4i_grid.cell_model_input
-- One row per land cell: the model's inputs, plus the label and holdout flag where measured.
-- Training, evaluation and prediction all read this one table, so every cell's features
-- are computed exactly the same way.
--
-- Two kinds of input:
--
--  1. nbr_offset_1km -- "nearby measured streets". Mean measured offset of TRAINING cells
--     (holdout = FALSE) within 1 km, EXCLUDING the cell's own 10x10-cell block (~1 km).
--       * Excluding the own block keeps a training cell from seeing its near-duplicate
--         neighbours on the same road; held-out cells and undriven cells get the same
--         definition, so the feature means the same thing everywhere.
--       * Holdout cells never contribute, so the holdout score stays honest.
--       * 0 (= the campaign mean) when no measured cell is in reach; nbr_n says how many
--         cells it averaged, a confidence signal for the agent.
--     Why it's here: offsets are strongly local (correlation 0.80 between cells 150 m apart,
--     0.19 at 1.2 km), and the built-environment features available today are too coarse
--     to capture that on their own (5-fold block cross-validation: R2 ~ 0 without it).
--
--  2. Built environment from a4i_grid.cell_built (see sql/grid/08_cell_built.sql).
--     Demographics are deliberately NOT inputs.

CREATE OR REPLACE TABLE a4i_grid.cell_model_input
CLUSTER BY cell_i, cell_j AS
WITH
blocked AS (
  SELECT
    c.cell_i, c.cell_j, c.center, c.in_training_range,
    FORMAT('%d:%d', CAST(FLOOR(c.cell_i / 10) AS INT64), CAST(FLOOR(c.cell_j / 10) AS INT64)) AS blk
  FROM a4i_grid.cells c
  WHERE c.is_land
),
train_cells AS (
  SELECT b.*, h.offset_f
  FROM blocked b
  JOIN a4i_grid.cell_heat h USING (cell_i, cell_j)
  WHERE NOT h.holdout
),
nbr AS (
  SELECT t.cell_i, t.cell_j, AVG(n.offset_f) AS nbr_offset_1km, COUNT(*) AS nbr_n
  FROM blocked t
  JOIN train_cells n
    ON n.blk != t.blk
   AND ST_DWITHIN(t.center, n.center, 1000)
  GROUP BY 1, 2
)
SELECT
  b.cell_i,
  b.cell_j,
  b.in_training_range,
  IFNULL(nbr.nbr_offset_1km, 0) AS nbr_offset_1km,
  IFNULL(nbr.nbr_n, 0)          AS nbr_n,
  bu.tract_water_share,
  bu.dist_open_space_m,
  bu.bg_housing_units_per_km2,
  bu.trees_100m,
  bu.tree_dbh_sum_100m,
  h.offset_f,                    -- NULL for undriven cells
  h.holdout                      -- NULL for undriven cells
FROM blocked b
JOIN a4i_grid.cell_built bu USING (cell_i, cell_j)
LEFT JOIN nbr USING (cell_i, cell_j)
LEFT JOIN a4i_grid.cell_heat h USING (cell_i, cell_j);
