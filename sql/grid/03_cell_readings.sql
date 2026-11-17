-- a4i_grid.cell_readings
-- HEAT LAYER, raw. Every Heat Watch reading, tagged with the grid cell it fell in.
-- This is the full measured record per cell: one afternoon, many readings.
--
--   cell_i = FLOOR(lat / 0.001), cell_j = FLOOR(lon / 0.001)   (~110 m x 85 m in Brooklyn)
--   offset_f            = temp_f minus the campaign mean (the whole city, same hour)
--   heat_index_offset_f = heat_index_f minus its campaign mean
--
-- observed_at is NULL for this campaign (NOAA didn't publish clock times for Brooklyn),
-- so readings can't be split by time of day.

CREATE OR REPLACE TABLE a4i_grid.cell_readings
CLUSTER BY cell_i, cell_j AS
SELECT
  CAST(FLOOR(latitude  / 0.001) AS INT64) AS cell_i,
  CAST(FLOOR(longitude / 0.001) AS INT64) AS cell_j,
  latitude,
  longitude,
  observed_at,
  temp_f,
  heat_index_f,
  humidity_pct,
  temp_f       - AVG(temp_f)       OVER () AS offset_f,
  heat_index_f - AVG(heat_index_f) OVER () AS heat_index_offset_f
FROM a4i_brooklyn.heat_observations
WHERE temp_f IS NOT NULL AND latitude IS NOT NULL AND longitude IS NOT NULL;
