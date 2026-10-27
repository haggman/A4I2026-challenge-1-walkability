WITH counts AS (
  SELECT
    (SELECT COUNT(*) FROM `PROJECT.a4i_semantic.dim_tract`) AS total_tracts,
    (SELECT COUNT(*) FROM `PROJECT.a4i_semantic.fact_heat_cell`) AS total_measured_cells
)
SELECT
  c.cell_id,
  c.block_id,
  ROUND(c.lat, 5) AS lat,
  ROUND(c.lon, 5) AS lon,
  c.n_readings,
  ROUND(c.mean_temp_f, 2) AS mean_temp_f,
  ROUND(c.campaign_mean_temp_f, 2) AS campaign_mean_temp_f,
  ROUND(c.offset_f, 2) AS offset_f,
  c.nearest_geo_id,
  counts.total_tracts,
  counts.total_measured_cells
FROM `PROJECT.a4i_semantic.fact_heat_cell` c
CROSS JOIN counts
WHERE c.n_readings >= GREATEST(@min_readings, 1)
ORDER BY c.offset_f DESC
LIMIT @limit
