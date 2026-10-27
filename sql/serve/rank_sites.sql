-- sql/serve/rank_sites.sql: Greedy non-overlapping Top 3 permanent walkable cooling center selection (>= 2 km spacing).
-- Reads: `qwiklabs-gcp-04-ec3596addc43.a4i_ml.grid_predictions`
WITH z AS (
  SELECT
    *,
    (predicted_offset_f - AVG(predicted_offset_f) OVER ()) / NULLIF(STDDEV(predicted_offset_f) OVER (), 0) AS z_hazard,
    (no_vehicle_rate    - AVG(no_vehicle_rate)    OVER ()) / NULLIF(STDDEV(no_vehicle_rate)    OVER (), 0) AS z_novehicle,
    (share_65_plus      - AVG(share_65_plus)      OVER ()) / NULLIF(STDDEV(share_65_plus)      OVER (), 0) AS z_age65,
    (poverty_rate       - AVG(poverty_rate)       OVER ()) / NULLIF(STDDEV(poverty_rate)       OVER (), 0) AS z_poverty,
    (total_pop          - AVG(total_pop)          OVER ()) / NULLIF(STDDEV(total_pop)          OVER (), 0) AS z_pop
  FROM `qwiklabs-gcp-04-ec3596addc43.a4i_ml.grid_predictions`
  WHERE predicted_offset_f > 0
    AND total_pop >= 1000
),
scored AS (
  SELECT
    point_id, lat, lon, geo_id, predicted_offset_f, unmeasured,
    drivers,
    total_pop, pop_65_plus, share_65_plus, car_free_households,
    median_age, poverty_rate, no_vehicle_rate, median_income,
    ST_GEOGPOINT(lon, lat) AS pt_geog,
    ROUND(
        0.35 * COALESCE(z_hazard, 0)
      + 0.25 * COALESCE(z_novehicle, 0)
      + 0.20 * COALESCE(z_age65, 0)
      + 0.15 * COALESCE(z_poverty, 0)
      + 0.05 * COALESCE(z_pop, 0),
      3
    ) AS priority_score
  FROM z
),
best_per_tract AS (
  SELECT *
  FROM scored
  QUALIFY ROW_NUMBER() OVER (PARTITION BY geo_id ORDER BY priority_score DESC, unmeasured DESC, point_id) = 1
),
site1 AS (
  SELECT * FROM best_per_tract ORDER BY priority_score DESC LIMIT 1
),
site2 AS (
  SELECT b.*
  FROM best_per_tract b
  CROSS JOIN site1 s1
  WHERE ST_DISTANCE(b.pt_geog, s1.pt_geog) >= 2000
  ORDER BY b.priority_score DESC
  LIMIT 1
),
site3 AS (
  SELECT b.*
  FROM best_per_tract b
  CROSS JOIN site1 s1
  CROSS JOIN site2 s2
  WHERE ST_DISTANCE(b.pt_geog, s1.pt_geog) >= 2000
    AND ST_DISTANCE(b.pt_geog, s2.pt_geog) >= 2000
  ORDER BY b.priority_score DESC
  LIMIT 1
)
SELECT 1 AS site_rank, * EXCEPT (pt_geog) FROM site1
UNION ALL
SELECT 2 AS site_rank, * EXCEPT (pt_geog) FROM site2
UNION ALL
SELECT 3 AS site_rank, * EXCEPT (pt_geog) FROM site3
ORDER BY site_rank;
