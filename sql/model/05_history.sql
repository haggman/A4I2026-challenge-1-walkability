-- a4i_grid.cell_heat_history_all, a4i_grid.cell_profile_full
-- Extends the estimated 2019-2025 history from the 1,020 driven cells to every land cell,
-- using offset_best_f (measured where driven, predicted elsewhere).
--
--   estimated local high for a day = reference daily high (Central Park/LGA/JFK) + offset_best_f
--
-- Same assumption as sql/grid/06_cell_heat_history.sql -- the afternoon offset holds on
-- every hot day -- plus, for undriven cells, the model's own error (~0.8 F on held-out blocks).

CREATE OR REPLACE TABLE a4i_grid.cell_heat_history_all
CLUSTER BY cell_i, cell_j AS
SELECT
  p.cell_i,
  p.cell_j,
  EXTRACT(YEAR FROM r.observation_date)              AS year,
  COUNTIF(r.ref_max_temp_f + p.offset_best_f >= 90)  AS est_days_ge_90,
  COUNTIF(r.ref_max_temp_f + p.offset_best_f >= 95)  AS est_days_ge_95,
  COUNTIF(r.ref_max_temp_f + p.offset_best_f >= 100) AS est_days_ge_100,
  MAX(r.ref_max_temp_f + p.offset_best_f)            AS est_peak_f
FROM a4i_grid.cell_heat_predicted p
CROSS JOIN a4i_grid.heat_reference_daily r
GROUP BY 1, 2, 3;

-- Everything about a cell in one row, including the model's view of it.
-- What the portal map and the agent's lookup tool should read once a model exists.
CREATE OR REPLACE VIEW a4i_grid.cell_profile_full AS
WITH hist AS (
  SELECT
    cell_i, cell_j,
    AVG(est_days_ge_90)  AS est_days_ge_90_per_year,
    AVG(est_days_ge_95)  AS est_days_ge_95_per_year,
    AVG(est_days_ge_100) AS est_days_ge_100_per_year,
    MAX(est_peak_f)      AS est_peak_f
  FROM a4i_grid.cell_heat_history_all
  GROUP BY 1, 2
)
SELECT
  c.* EXCEPT (center),
  p.offset_best_f,
  p.measured_offset_f,
  p.predicted_offset_f,
  p.confidence,
  p.attributions,
  h.* EXCEPT (cell_i, cell_j),
  b.* EXCEPT (cell_i, cell_j),
  i.* EXCEPT (cell_i, cell_j, bg_geo_id, tract_geo_id)
FROM a4i_grid.cells c
LEFT JOIN a4i_grid.cell_heat_predicted p USING (cell_i, cell_j)
LEFT JOIN hist h                         USING (cell_i, cell_j)
LEFT JOIN a4i_grid.cell_built b          USING (cell_i, cell_j)
LEFT JOIN a4i_grid.cell_impact i         USING (cell_i, cell_j);
