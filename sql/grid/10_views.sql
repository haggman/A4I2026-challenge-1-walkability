-- Views over the grid. Nothing is copied; they always reflect the tables.

-- training_examples: built-environment features + the label, for CREATE MODEL / ML.EVALUATE.
-- Train on holdout = FALSE, evaluate on holdout = TRUE. Drop cell_i, cell_j, holdout and
-- n_readings from the model's input (or use n_readings as a sample weight).
CREATE OR REPLACE VIEW a4i_grid.training_examples AS
SELECT
  b.*,
  h.holdout,
  h.n_readings,
  h.offset_f
FROM a4i_grid.cell_built b
JOIN a4i_grid.cell_heat h USING (cell_i, cell_j);

-- cell_heat_summary: one row per driven cell, the 2019-2025 history rolled up.
-- trend_days_ge_95_per_year is a least-squares slope over 7 points: weak evidence, show
-- it with that caveat.
CREATE OR REPLACE VIEW a4i_grid.cell_heat_summary AS
SELECT
  cell_i,
  cell_j,
  AVG(est_days_ge_90)   AS est_days_ge_90_per_year,
  AVG(est_days_ge_95)   AS est_days_ge_95_per_year,
  AVG(est_days_ge_100)  AS est_days_ge_100_per_year,
  MAX(est_peak_f)       AS est_peak_f,
  SAFE_DIVIDE(COVAR_POP(year, est_days_ge_95), VAR_POP(year)) AS trend_days_ge_95_per_year
FROM a4i_grid.cell_heat_history
GROUP BY cell_i, cell_j;

-- cell_profile: everything about one cell in one row. What the portal map and the agent's
-- lookup tool read. Heat columns are NULL for undriven cells until predictions exist.
CREATE OR REPLACE VIEW a4i_grid.cell_profile AS
SELECT
  c.* EXCEPT (center),
  h.offset_f,
  h.heat_index_offset_f,
  h.n_readings,
  h.holdout,
  s.est_days_ge_90_per_year,
  s.est_days_ge_95_per_year,
  s.est_days_ge_100_per_year,
  s.est_peak_f,
  s.trend_days_ge_95_per_year,
  b.* EXCEPT (cell_i, cell_j),
  i.* EXCEPT (cell_i, cell_j, bg_geo_id, tract_geo_id)
FROM a4i_grid.cells c
LEFT JOIN a4i_grid.cell_heat h          USING (cell_i, cell_j)
LEFT JOIN a4i_grid.cell_heat_summary s  USING (cell_i, cell_j)
LEFT JOIN a4i_grid.cell_built b         USING (cell_i, cell_j)
LEFT JOIN a4i_grid.cell_impact i        USING (cell_i, cell_j);
