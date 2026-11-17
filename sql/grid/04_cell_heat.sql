-- a4i_grid.cell_heat
-- HEAT LAYER, per cell. One row per driven cell with >= 5 readings.
-- offset_f is the BigQuery ML training label. None of these columns are model features.
--
--   holdout = whole 10x10-cell blocks (~1 km) held out together (~20%), so neighbouring
--             cells on the same road can't leak between train and test.

CREATE OR REPLACE TABLE a4i_grid.cell_heat AS
SELECT
  cell_i,
  cell_j,
  AVG(offset_f)                                   AS offset_f,
  APPROX_QUANTILES(offset_f, 2)[OFFSET(1)]        AS offset_median_f,
  STDDEV(offset_f)                                AS offset_sd_f,
  MIN(offset_f)                                   AS offset_min_f,
  MAX(offset_f)                                   AS offset_max_f,
  AVG(heat_index_offset_f)                        AS heat_index_offset_f,
  AVG(temp_f)                                     AS campaign_temp_f,
  AVG(heat_index_f)                               AS campaign_heat_index_f,
  COUNT(*)                                        AS n_readings,
  MOD(ABS(FARM_FINGERPRINT(FORMAT('%d:%d',
      CAST(FLOOR(cell_i / 10) AS INT64), CAST(FLOOR(cell_j / 10) AS INT64)))), 5) = 0 AS holdout
FROM a4i_grid.cell_readings
GROUP BY cell_i, cell_j
HAVING COUNT(*) >= 5;
