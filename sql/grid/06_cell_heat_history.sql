-- a4i_grid.cell_heat_history
-- HEAT LAYER, estimated history per cell and year (driven cells only for now).
--
--   estimated local high for a day = reference daily high + the cell's offset_f
--
-- ASSUMPTION, say it out loud: the cell's offset from one afternoon holds on every hot day.
-- That's the notebook's own premise (the spatial pattern is stable because buildings and
-- roads don't move), but these are ESTIMATES, not measurements. Undriven cells get rows
-- once the model has predicted their offset (swap offset_f for the prediction).

CREATE OR REPLACE TABLE a4i_grid.cell_heat_history AS
SELECT
  h.cell_i,
  h.cell_j,
  EXTRACT(YEAR FROM r.observation_date)            AS year,
  COUNTIF(r.ref_max_temp_f + h.offset_f >= 90)     AS est_days_ge_90,
  COUNTIF(r.ref_max_temp_f + h.offset_f >= 95)     AS est_days_ge_95,
  COUNTIF(r.ref_max_temp_f + h.offset_f >= 100)    AS est_days_ge_100,
  MAX(r.ref_max_temp_f + h.offset_f)               AS est_peak_f
FROM a4i_grid.cell_heat h
CROSS JOIN a4i_grid.heat_reference_daily r
GROUP BY 1, 2, 3;
