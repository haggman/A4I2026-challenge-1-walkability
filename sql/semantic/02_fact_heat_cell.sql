-- sql/semantic/02_fact_heat_cell.sql
-- Purpose : Aggregate 1 Hz Heat Watch readings into ~150 m (geohash-7) spatial cells with offset_f (°F above campaign mean) and nearest census tract.
-- Inputs  : `qwiklabs-gcp-04-ec3596addc43.a4i_core.heat_readings`,
--           `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts`
-- Outputs : `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_heat_cell`
-- Owner   : data lane
-- Why     : 1 Hz mobile traverse points along a road are spatially autocorrelated and contain 4,052
--           near-duplicate 4-decimal points. Aggregating to geohash-7 (~153 m x 153 m) cells collapses
--           23,386 readings into 2,020 cells and defines offset_f = cell_mean_temp_f - campaign_mean_temp_f.
--           Outlier exclusion rule: excludes readings where is_temp_outlier = TRUE (|temp_f - campaign_mean| > 4 SD)
--           via `WHERE NOT is_temp_outlier` (0 readings excluded in Atlanta; documented and reversible).
--
-- Example query:
--   SELECT cell_id, lat, lon, n_readings, ROUND(offset_f, 2) AS offset_f, nearest_geo_id
--   FROM `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_heat_cell`
--   WHERE n_readings >= 3
--   ORDER BY offset_f DESC
--   LIMIT 15;

CREATE OR REPLACE VIEW `qwiklabs-gcp-04-ec3596addc43.a4i_semantic.fact_heat_cell`
(
  cell_id OPTIONS (description = 'Geohash-7 spatial cell identifier (~153 m x 153 m).'),
  block_id OPTIONS (description = 'Geohash-5 spatial block identifier (~4.9 km x 4.9 km) used for spatial-block train/eval splits.'),
  lat OPTIONS (description = 'Cell centroid latitude across non-outlier traverse readings (degrees North, WGS84).'),
  lon OPTIONS (description = 'Cell centroid longitude across non-outlier traverse readings (degrees East, WGS84).'),
  n_readings OPTIONS (description = 'Number of non-outlier 1 Hz traverse readings aggregated in the cell (count).'),
  n_stationary_readings OPTIONS (description = 'Number of readings in the cell flagged as stationary vehicle clusters (count).'),
  mean_temp_f OPTIONS (description = 'Cell mean drive-day temperature (deg F; historical campaign reference, always present via offset_f).'),
  campaign_mean_temp_f OPTIONS (description = 'Atlanta campaign-wide mean temperature across all non-outlier traverse readings (deg F).'),
  offset_f OPTIONS (description = 'Heat offset: cell mean temperature minus Atlanta campaign mean temperature (deg F above/below city average).'),
  nearest_geo_id OPTIONS (description = '11-character FIPS geo_id of the census tract whose internal point is nearest to the cell centroid (string).'),
  meters_to_nearest_tract OPTIONS (description = 'Straight-line distance from cell centroid to nearest census tract internal point (meters).')
)
OPTIONS (
  description = 'Aggregated ~150 m (geohash-7) Heat Watch cells for Atlanta (2,020 cells). Excludes readings flagged is_temp_outlier = TRUE (> 4 SD from campaign mean). Computes offset_f = mean_temp_f - campaign_mean_temp_f and links each cell to its nearest census tract.',
  labels = [('app', 'heat-planner'), ('lane', 'data'), ('layer', 'semantic')]
) AS
WITH valid_readings AS (
  SELECT
    cell_id,
    latitude,
    longitude,
    temp_f,
    is_stationary_cluster,
    AVG(temp_f) OVER () AS campaign_mean_temp_f
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_core.heat_readings`
  WHERE NOT is_temp_outlier
),
cells AS (
  SELECT
    cell_id,
    SUBSTR(cell_id, 1, 5) AS block_id,
    AVG(latitude) AS lat,
    AVG(longitude) AS lon,
    ST_GEOGPOINT(AVG(longitude), AVG(latitude)) AS cell_geog,
    COUNT(*) AS n_readings,
    COUNTIF(is_stationary_cluster) AS n_stationary_readings,
    AVG(temp_f) AS mean_temp_f,
    ANY_VALUE(campaign_mean_temp_f) AS campaign_mean_temp_f,
    AVG(temp_f) - ANY_VALUE(campaign_mean_temp_f) AS offset_f
  FROM valid_readings
  GROUP BY cell_id
),
nearest_tract AS (
  SELECT
    c.cell_id,
    ARRAY_AGG(
      STRUCT(
        t.geo_id AS nearest_geo_id,
        ST_DISTANCE(c.cell_geog, t.tract_centroid_geog) AS meters_to_nearest_tract
      )
      ORDER BY ST_DISTANCE(c.cell_geog, t.tract_centroid_geog)
      LIMIT 1
    )[OFFSET(0)] AS nt
  FROM cells c
  JOIN `qwiklabs-gcp-04-ec3596addc43.a4i_core.tracts` t
    ON ST_DWITHIN(c.cell_geog, t.tract_centroid_geog, 10000)
  GROUP BY c.cell_id
)
SELECT
  c.cell_id,
  c.block_id,
  c.lat,
  c.lon,
  c.n_readings,
  c.n_stationary_readings,
  ROUND(c.mean_temp_f, 3) AS mean_temp_f,
  ROUND(c.campaign_mean_temp_f, 3) AS campaign_mean_temp_f,
  ROUND(c.offset_f, 3) AS offset_f,
  n.nt.nearest_geo_id,
  ROUND(n.nt.meters_to_nearest_tract, 1) AS meters_to_nearest_tract
FROM cells c
LEFT JOIN nearest_tract n USING (cell_id);
