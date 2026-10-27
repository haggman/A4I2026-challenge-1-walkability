# Data Dictionary — `qwiklabs-gcp-04-ec3596addc43` (`a4i_core`, `a4i_semantic`, `a4i_ml`)

> **Generated directly from BigQuery `INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`** across `a4i_core`, `a4i_semantic`, and `a4i_ml`.
> Every table and view column has an explicit `OPTIONS(description = ...)` registered in the BigQuery catalog.

## Summary Coverage

| Layer / Schema | Object Name | Object Type | Grain | Row Count | Columns Described |
|---|---|---|---|---:|---:|
| `a4i_core` | `heat_readings` | TABLE (Partitioned by obs_date, Clustered by geohash_5, tract_geoid) | One cleaned Heat Watch mobile traverse reading (`reading_id`, 1 Hz road point) | 23,386 | 14/14 |
| `a4i_core` | `station_days` | TABLE (Partitioned by observation_date, Clustered by station_id) | One GHCN station × calendar day (`station_id`, `observation_date`) | 17,452 | 8/8 |
| `a4i_core` | `tracts` | TABLE (Clustered by geo_id) | One Census tract in the Atlanta study area (11-character FIPS `geo_id`) | 353 | 21/21 |
| `a4i_semantic` | `dim_tract` | VIEW | One Census tract (`tract_geoid`) | 353 | 18/18 |
| `a4i_semantic` | `fact_heat_cell` | TABLE (Clustered by spatial_block_id, tract_geoid) | One geohash-7 cell (~150 m × 150 m, `cell_id`) visited by the Heat Watch campaign | 2,020 (across 22 geohash-5 spatial blocks) | 11/11 |
| `a4i_semantic` | `fact_city_heat_day` | VIEW | One calendar date (`observation_date`) for the city of Atlanta | 2,557 (2019-01-01 through 2025-12-31) | 4/4 |
| `a4i_semantic` | `metric_city_heat_days_by_year` | VIEW | One calendar year (`obs_year`, 2019–2025) | 7 | 10/10 |
| `a4i_semantic` | `audit_city_baseline` | VIEW | One row representing the entire Atlanta study area (`scope = "CITY_ALL_TRACTS"`) | 1 | 11/11 |
| `a4i_ml` | `tracts_enriched` | TABLE (Clustered by geo_id) | One Census tract (`geo_id`, 11-character FIPS) | 353 | 19/19 |
| `a4i_ml` | `campaign_footprint` | TABLE | One single-row reference table for the Atlanta campaign footprint | 1 | 3/3 |
| `a4i_semantic` | `site_hot_days(offset_f)` | TABLE FUNCTION (TVF) | One row summarizing projected hot days/year for a site with `+offset_f` °F | 1 (per call) | 9 output columns |
| `a4i_semantic` | `vulnerable_population(lat, lon, radius_m)` | TABLE FUNCTION (TVF) | One Census tract intersecting the catchment buffer (`radius_m` meters around `lat, lon`) | Variable (tracts in catchment) | 16 output columns |
| `a4i_ml` | `point_features(pts)` | TABLE FUNCTION (TVF) | One candidate coordinate (`point_id`, `lat`, `lon`) from input array | `ARRAY_LENGTH(pts)` | 20 output columns |

## `a4i_core.heat_readings`

- **Type:** TABLE (Partitioned by obs_date, Clustered by geohash_5, tract_geoid)
- **Grain:** One cleaned Heat Watch mobile traverse reading (`reading_id`, 1 Hz road point)
- **Row Count:** 23,386
- **Purpose:** Cleaned Atlanta Heat Watch observations with heat_offset_f (°F above city campaign mean 82.062°F), 20m spatial density weight, and geohash-5/geohash-7 spatial keys.

| Column | Data Type | Description (`INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`) |
|---|---|---|
| `reading_id` | `STRING` | Deterministic unique identifier for the traverse reading (string, atl_hr_NNNNN). |
| `city` | `STRING` | Campaign city name (string, populated as Atlanta where raw was NULL). |
| `latitude` | `FLOAT64` | Reading latitude (degrees North, WGS84). |
| `longitude` | `FLOAT64` | Reading longitude (degrees East, WGS84). |
| `geog` | `GEOGRAPHY` | Point geography of reading (GEOGRAPHY, ST_GEOGPOINT(longitude, latitude)). |
| `cell_id` | `STRING` | Geohash-7 spatial cell identifier (~153 m x 153 m). |
| `temp_f` | `FLOAT64` | Drive-day ambient air temperature (deg F, range-checked 40-140 deg F; label-side only, never a model feature). |
| `heat_index_f` | `FLOAT64` | Drive-day heat index (deg F, 40-160 deg F or NULL; never a model feature). |
| `humidity_pct` | `FLOAT64` | Drive-day relative humidity (%, 0-100 or NULL; never a model feature). |
| `observed_at` | `TIMESTAMP` | Drive-day reading timestamp (UTC TIMESTAMP; never a model feature). |
| `neighbors_within_20m` | `INT64` | Wait-spot density: count of other traverse readings within 20 meters (count). |
| `is_stationary_cluster` | `BOOL` | Reversible boolean flag: TRUE when >=10 other readings fall within 20 m (stationary vehicle cluster). |
| `temp_zscore` | `FLOAT64` | Standardized temperature z-score relative to the campaign mean (SD units). |
| `is_temp_outlier` | `BOOL` | Reversible boolean flag: TRUE when temp_f is beyond +-4 SD from the campaign mean. |

## `a4i_core.station_days`

- **Type:** TABLE (Partitioned by observation_date, Clustered by station_id)
- **Grain:** One GHCN station × calendar day (`station_id`, `observation_date`)
- **Row Count:** 17,452
- **Purpose:** Cleaned GHCN daily maximum temperature records across 7 Atlanta stations (2019-01-01 to 2025-12-31) with precomputed 90/95/100/105°F threshold flags.

| Column | Data Type | Description (`INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`) |
|---|---|---|
| `station_id` | `STRING` | GHCN-Daily weather station identifier (string, e.g., USW00013874). |
| `station_name` | `STRING` | Official NOAA GHCN weather station name (string). |
| `observation_date` | `DATE` | Calendar date of daily maximum temperature reading (DATE). |
| `latitude` | `FLOAT64` | Station latitude (degrees North, WGS84). |
| `longitude` | `FLOAT64` | Station longitude (degrees East, WGS84). |
| `station_geog` | `GEOGRAPHY` | Point geography of weather station (GEOGRAPHY, ST_GEOGPOINT(longitude, latitude)). |
| `max_temp_f` | `FLOAT64` | Daily maximum air temperature recorded at station (deg F, range-checked -60 to 140 deg F). |
| `dist_to_campaign_center_km` | `FLOAT64` | Straight-line distance from station to the Atlanta Heat Watch traverse centroid (km). |

## `a4i_core.tracts`

- **Type:** TABLE (Clustered by geo_id)
- **Grain:** One Census tract in the Atlanta study area (11-character FIPS `geo_id`)
- **Row Count:** 353
- **Purpose:** Cleaned Census tracts with LPAD(geo_id,11,'0'), NULLIF sentinel cleaning, ACS 2020 5-yr age 65+ counts/rates, and US Census TIGER polygon geometries & land/water areas.

| Column | Data Type | Description (`INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`) |
|---|---|---|
| `geo_id` | `STRING` | 11-character FIPS census tract identifier (string, LPAD(geo_id, 11, 0)). |
| `tract_lat` | `FLOAT64` | Tract internal-point latitude (degrees North, WGS84). |
| `tract_lon` | `FLOAT64` | Tract internal-point longitude (degrees East, WGS84). |
| `tract_centroid_geog` | `GEOGRAPHY` | Tract internal-point geography (GEOGRAPHY, ST_GEOGPOINT(tract_lon, tract_lat)). |
| `total_pop` | `FLOAT64` | Total resident population in tract (persons, ACS 2020 5-yr). |
| `pop_65_plus` | `FLOAT64` | Residents aged 65 years and older (persons, sum of 12 ACS male/female 65+ brackets). |
| `share_65_plus` | `FLOAT64` | Share of tract population aged 65+ (share 0-1, NULL when total_pop=0). |
| `households` | `FLOAT64` | Occupied housing units / households in tract (households). |
| `housing_units` | `FLOAT64` | Total housing units in tract (units). |
| `no_cars` | `FLOAT64` | Car-free households: occupied housing units with zero vehicles available (households). |
| `no_vehicle_rate` | `FLOAT64` | Share of households with no vehicle available (share 0-1). |
| `poverty_rate` | `FLOAT64` | Share of population with income below the federal poverty level (share 0-1). |
| `median_age` | `FLOAT64` | Median age of tract residents (years; ACS -666666666 sentinel cleaned to NULL). |
| `median_income` | `FLOAT64` | Median household income in past 12 months (USD; ACS -666666666 sentinel cleaned to NULL). |
| `median_year_structure_built` | `FLOAT64` | Median year residential structures were built (calendar year 1900-2025; sentinels/zeros cleaned to NULL). |
| `area_land_m2` | `FLOAT64` | Tract land area (square meters, US Census TIGER). |
| `area_water_m2` | `FLOAT64` | Tract water area (square meters, US Census TIGER). |
| `land_area_km2` | `FLOAT64` | Tract land area (km2). |
| `pop_density_km2` | `FLOAT64` | Population density per square kilometer of land (persons per km2). |
| `housing_density_km2` | `FLOAT64` | Housing unit density per square kilometer of land (housing units per km2). |
| `water_share` | `FLOAT64` | Share of total tract area covered by water (share 0-1). |

## `a4i_semantic.dim_tract`

- **Type:** VIEW
- **Grain:** One Census tract (`tract_geoid`)
- **Row Count:** 353
- **Purpose:** Planner-facing tract dimension with non-racial vulnerability percentile (equal-weight rank average of poverty_rate, no_vehicle_rate, pct_age_65_plus, and inverse median_income) and quartile tier (1=Lowest, 4=Highest).

| Column | Data Type | Description (`INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`) |
|---|---|---|
| `geo_id` | `STRING` | 11-character FIPS census tract identifier (string). |
| `centroid_lat` | `FLOAT64` | Tract internal-point centroid latitude (degrees North, WGS84). |
| `centroid_lon` | `FLOAT64` | Tract internal-point centroid longitude (degrees East, WGS84). |
| `population` | `FLOAT64` | Total resident population in the tract (persons, ACS 2020 5-yr). |
| `pop_65_plus` | `FLOAT64` | Residents aged 65 years and older (persons, ACS 2020 5-yr). |
| `share_65_plus` | `FLOAT64` | Share of tract population aged 65 years and older (share 0-1). |
| `car_free_households` | `FLOAT64` | Occupied households with zero vehicles available (households). |
| `households` | `FLOAT64` | Total occupied households in the tract (households). |
| `housing_units` | `FLOAT64` | Total housing units in the tract (housing units). |
| `no_vehicle_rate` | `FLOAT64` | Share of occupied households with no vehicle available (share 0-1). |
| `poverty_rate` | `FLOAT64` | Share of tract population below the federal poverty level (share 0-1). |
| `median_income` | `FLOAT64` | Median household income in the past 12 months (USD, sentinel-cleaned). |
| `median_age` | `FLOAT64` | Median resident age (years, sentinel-cleaned). |
| `median_year_built` | `FLOAT64` | Median year residential structures were built (calendar year 1900-2025). |
| `land_area_km2` | `FLOAT64` | Tract land area (square kilometers, km2). |
| `pop_density_km2` | `FLOAT64` | Population density per square kilometer of land (persons per km2). |
| `housing_density_km2` | `FLOAT64` | Housing unit density per square kilometer of land (housing units per km2). |
| `water_share` | `FLOAT64` | Share of total tract area covered by water (share 0-1). |

## `a4i_semantic.fact_heat_cell`

- **Type:** TABLE (Clustered by spatial_block_id, tract_geoid)
- **Grain:** One geohash-7 cell (~150 m × 150 m, `cell_id`) visited by the Heat Watch campaign
- **Row Count:** 2,020 (across 22 geohash-5 spatial blocks)
- **Purpose:** De-autocorrelated heat cells aggregating 1 Hz road readings into ~150 m grid cells with mean/max heat_offset_f (°F above campaign mean), assigned tract_geoid, and geohash-5 spatial_block_id.

| Column | Data Type | Description (`INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`) |
|---|---|---|
| `cell_id` | `STRING` | Geohash-7 spatial cell identifier (~153 m x 153 m). |
| `block_id` | `STRING` | Geohash-5 spatial block identifier (~4.9 km x 4.9 km) used for spatial-block train/eval splits. |
| `lat` | `FLOAT64` | Cell centroid latitude across non-outlier traverse readings (degrees North, WGS84). |
| `lon` | `FLOAT64` | Cell centroid longitude across non-outlier traverse readings (degrees East, WGS84). |
| `n_readings` | `INT64` | Number of non-outlier 1 Hz traverse readings aggregated in the cell (count). |
| `n_stationary_readings` | `INT64` | Number of readings in the cell flagged as stationary vehicle clusters (count). |
| `mean_temp_f` | `FLOAT64` | Cell mean drive-day temperature (deg F; historical campaign reference, always present via offset_f). |
| `campaign_mean_temp_f` | `FLOAT64` | Atlanta campaign-wide mean temperature across all non-outlier traverse readings (deg F). |
| `offset_f` | `FLOAT64` | Heat offset: cell mean temperature minus Atlanta campaign mean temperature (deg F above/below city average). |
| `nearest_geo_id` | `STRING` | 11-character FIPS geo_id of the census tract whose internal point is nearest to the cell centroid (string). |
| `meters_to_nearest_tract` | `FLOAT64` | Straight-line distance from cell centroid to nearest census tract internal point (meters). |

## `a4i_semantic.fact_city_heat_day`

- **Type:** VIEW
- **Grain:** One calendar date (`observation_date`) for the city of Atlanta
- **Row Count:** 2,557 (2019-01-01 through 2025-12-31)
- **Purpose:** Daily city-wide reference maximum temperature (mean of daily max across reporting GHCN stations) used for heat-frequency calculations.

| Column | Data Type | Description (`INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`) |
|---|---|---|
| `date` | `DATE` | Calendar date of observation (DATE, 2019-01-01 to 2025-12-31). |
| `city_max_temp_f` | `FLOAT64` | Maximum daily air temperature recorded across all reporting Atlanta GHCN stations on that date (deg F). |
| `city_mean_station_max_temp_f` | `FLOAT64` | Mean of daily maximum air temperatures across reporting Atlanta GHCN stations on that date (deg F). |
| `n_stations_reporting` | `INT64` | Number of Atlanta GHCN stations reporting on that date (count). |

## `a4i_semantic.metric_city_heat_days_by_year`

- **Type:** VIEW
- **Grain:** One calendar year (`obs_year`, 2019–2025)
- **Row Count:** 7
- **Purpose:** Annual GHCN station-history summary of city-wide heat days ≥90°F, ≥95°F, ≥100°F, ≥105°F, summer average daily max, and hottest day per year.

| Column | Data Type | Description (`INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`) |
|---|---|---|
| `year` | `INT64` | Calendar year (INT64, full years with >=300 reporting days only). |
| `days_reported` | `INT64` | Number of calendar days with station coverage in the year (days, >=300). |
| `days_ge_90_f` | `INT64` | Days in the year when city_max_temp_f reached >= 90 deg F (days). |
| `days_ge_95_f` | `INT64` | Days in the year when city_max_temp_f reached >= 95 deg F (days). |
| `days_ge_100_f` | `INT64` | Days in the year when city_max_temp_f reached >= 100 deg F (days). |
| `hottest_temp_f` | `FLOAT64` | Highest station daily maximum temperature recorded in the year (deg F). |
| `mean_days_ge_90_f` | `FLOAT64` | Multi-year mean of annual days >= 90 deg F across full years (days/yr). |
| `mean_days_ge_95_f` | `FLOAT64` | Multi-year mean of annual days >= 95 deg F across full years (days/yr). |
| `mean_days_ge_100_f` | `FLOAT64` | Multi-year mean of annual days >= 100 deg F across full years (days/yr). |
| `ols_slope_days_ge_95_per_yr` | `FLOAT64` | OLS linear slope of annual days >= 95 deg F per year (days/yr/yr; caveat: 7 years reflects weather variability, not a climate trend). |

## `a4i_semantic.audit_city_baseline`

- **Type:** VIEW
- **Grain:** One row representing the entire Atlanta study area (`scope = "CITY_ALL_TRACTS"`)
- **Row Count:** 1
- **Purpose:** Population-weighted and household-weighted citywide demographic baseline for the post-hoc equity audit of recommended cooling center sites.

| Column | Data Type | Description (`INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`) |
|---|---|---|
| `populated_tracts` | `INT64` | Number of census tracts with total_pop > 0 included in the city baseline (tracts). |
| `total_population` | `FLOAT64` | Total resident population across all tracts (persons). |
| `total_pop_65_plus` | `FLOAT64` | Total residents aged 65+ across all tracts (persons). |
| `total_car_free_households` | `FLOAT64` | Total car-free households across all tracts (households). |
| `city_median_income_usd` | `FLOAT64` | Population-weighted mean of tract median household income across populated tracts with non-null income (USD). |
| `city_poverty_rate` | `FLOAT64` | Population-weighted poverty rate across populated tracts (share 0-1). |
| `city_no_vehicle_rate` | `FLOAT64` | Population-weighted no-vehicle household rate across populated tracts (share 0-1). |
| `city_share_65_plus` | `FLOAT64` | Population-weighted share of residents aged 65 years and older (share 0-1). |
| `city_median_age_years` | `FLOAT64` | Population-weighted mean of tract median age across populated tracts (years). |
| `city_share_in_top_poverty_quintile` | `FLOAT64` | Share of city population living in the top quintile (top 20%) of tracts by poverty_rate (share 0-1). |
| `top_poverty_quintile_threshold` | `FLOAT64` | Minimum tract poverty_rate for the top poverty quintile (share 0-1). |

## `a4i_ml.tracts_enriched`

- **Type:** TABLE (Clustered by geo_id)
- **Grain:** One Census tract (`geo_id`, 11-character FIPS)
- **Row Count:** 353
- **Purpose:** ML feature backbone per Census tract with cleaned demographics, ACS 65+ share, TIGER land/water ratio, population/housing density, and median-imputed model-ready feature columns (`feat_*`).

| Column | Data Type | Description (`INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`) |
|---|---|---|
| `geo_id` | `STRING` | 11-character FIPS census tract identifier (string). |
| `tract_lat` | `FLOAT64` | Tract internal-point latitude (degrees North, WGS84). |
| `tract_lon` | `FLOAT64` | Tract internal-point longitude (degrees East, WGS84). |
| `tract_centroid_geog` | `GEOGRAPHY` | Tract internal-point geography (GEOGRAPHY). |
| `total_pop` | `FLOAT64` | Total resident population in tract (persons). |
| `housing_units` | `FLOAT64` | Total housing units in tract (units). |
| `households` | `FLOAT64` | Total occupied households in tract (households). |
| `median_year_built` | `FLOAT64` | Median year residential structures were built (calendar year 1900-2025; sentinel-cleaned). |
| `land_area_km2` | `FLOAT64` | Tract land area (km2). |
| `pop_density_km2` | `FLOAT64` | Population density per square kilometer of land (persons per km2). |
| `housing_density_km2` | `FLOAT64` | Housing unit density per square kilometer of land (units per km2). |
| `water_share` | `FLOAT64` | Share of total tract area covered by water (share 0-1). |
| `pop_65_plus` | `FLOAT64` | Residents aged 65+ (persons; ranking/audit context only, never a model feature). |
| `share_65_plus` | `FLOAT64` | Share of residents aged 65+ (share 0-1; ranking/audit context only, never a model feature). |
| `car_free_households` | `FLOAT64` | Occupied households with zero vehicles available (households; ranking/audit context only). |
| `median_age` | `FLOAT64` | Median resident age (years, sentinel-cleaned; ranking/audit context only). |
| `median_income` | `FLOAT64` | Median household income (USD, sentinel-cleaned; ranking/audit context only). |
| `poverty_rate` | `FLOAT64` | Share of population below federal poverty level (share 0-1; ranking/audit context only). |
| `no_vehicle_rate` | `FLOAT64` | Share of households with no vehicle available (share 0-1; ranking/audit context only). |

## `a4i_ml.campaign_footprint`

- **Type:** TABLE
- **Grain:** One single-row reference table for the Atlanta campaign footprint
- **Row Count:** 1
- **Purpose:** Stores the convex hull polygon of all 23,386 Atlanta Heat Watch readings, the union of 500 m buffers (`footprint_500m_geom`), and `campaign_mean_f` (82.062 °F).

| Column | Data Type | Description (`INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`) |
|---|---|---|
| `footprint` | `GEOGRAPHY` | 1,000 m buffered convex hull polygon of the Atlanta Heat Watch traverse (GEOGRAPHY). |
| `center` | `GEOGRAPHY` | Centroid point geography of the Atlanta Heat Watch traverse (GEOGRAPHY). |
| `campaign_mean_f` | `FLOAT64` | Atlanta campaign mean temperature across non-outlier traverse readings (deg F, 82.062 F). |

## Table-Valued Functions (TVFs)

### `a4i_semantic.site_hot_days(offset_f FLOAT64)`
- **DDL Source:** `sql/semantic/05_tvf_site_hot_days.sql`
- **Signature:** `a4i_semantic.site_hot_days(offset_f FLOAT64)`
- **Purpose:** Answers *"Given a site with a predicted heat offset of `+offset_f` °F above the city mean, how many days per year does that site effectively experience ≥90°F, ≥95°F, ≥100°F, and ≥105°F based on Atlanta's 2019–2025 GHCN station history?"*

| Output Column | Data Type | Description |
|---|---|---|
| `assumed_offset_f` | `FLOAT64` | Input heat offset (`°F` above city mean) evaluated for the candidate site. |
| `years_covered` | `INT64` | Number of distinct GHCN calendar years in the baseline (7 years: 2019–2025). |
| `city_days_ge_90f_per_yr` | `FLOAT64` | Baseline city-wide days/year where `city_max_temp_f >= 90°F` (zero offset). |
| `site_days_ge_90f_per_yr` | `FLOAT64` | Projected days/year where `city_max_temp_f + offset_f >= 90°F` at this site. |
| `site_days_ge_95f_per_yr` | `FLOAT64` | Projected days/year where `city_max_temp_f + offset_f >= 95°F` at this site. |
| `site_days_ge_100f_per_yr` | `FLOAT64` | Projected days/year where `city_max_temp_f + offset_f >= 100°F` at this site. |
| `site_days_ge_105f_per_yr` | `FLOAT64` | Projected days/year where `city_max_temp_f + offset_f >= 105°F` at this site. |
| `extra_days_ge_95f_vs_city` | `FLOAT64` | Additional ≥95°F days/year at this site compared to the city baseline (`city_max_temp_f >= 95°F`). |
| `extra_days_ge_100f_vs_city` | `FLOAT64` | Additional ≥100°F days/year at this site compared to the city baseline (`city_max_temp_f >= 100°F`). |

### `a4i_semantic.vulnerable_population(lat FLOAT64, lon FLOAT64, radius_m FLOAT64)`
- **DDL Source:** `sql/semantic/06_tvf_vulnerable_population.sql`
- **Signature:** `a4i_semantic.vulnerable_population(lat FLOAT64, lon FLOAT64, radius_m FLOAT64)`
- **Purpose:** Computes area-weighted population, seniors (65+), households without vehicles, and poverty indicators for all Census tracts intersecting a `radius_m`-meter catchment buffer around `(lat, lon)`.

| Output Column | Data Type | Description |
|---|---|---|
| `query_lat`, `query_lon`, `radius_m` | `FLOAT64` | Input candidate coordinate and catchment radius in meters. |
| `tract_geoid` | `STRING` | 11-character FIPS code of the intersecting Census tract. |
| `overlap_Weight` | `FLOAT64` | Area-intersection weight (`[0, 1]`) of the tract polygon within the catchment circle. |
| `distance_to_tract_center_m` | `FLOAT64` | Distance in meters from `(lat, lon)` to the tract centroid. |
| `tract_total_pop` | `INT64` | Total residents in the full Census tract. |
| `est_pop_in_radius` | `INT64` | Area-weighted estimated residents inside the catchment buffer. |
| `est_pop_age_65_plus_in_radius` | `INT64` | Area-weighted estimated seniors (age 65+) inside the catchment buffer. |
| `est_no_car_hh_in_radius` | `INT64` | Area-weighted estimated zero-vehicle households inside the catchment buffer. |
| `poverty_rate`, `no_vehicle_rate`, `pct_age_65_plus`, `median_income` | `FLOAT64` | Tract-level socioeconomic vulnerability indicators. |
| `vulnerability_pct`, `vulnerability_tier` | `FLOAT64`, `INT64` | Non-racial composite vulnerability percentile (`[0, 1]`) and quartile tier (`1..4`). |

### `a4i_ml.point_features(pts ARRAY<STRUCT<point_id STRING, lat FLOAT64, lon FLOAT64>>)`
- **DDL Source:** `sql/ml/01_features.sql`
- **Signature:** `a4i_ml.point_features(pts ARRAY<STRUCT<point_id STRING, lat FLOAT64, lon FLOAT64>>)`
- **Purpose:** Single source of truth for ML feature assembly at any candidate `(lat, lon)`. Used identically by `a4i_ml` training/grid tables and the agent's `ML.EXPLAIN_PREDICT` tool. Never touches `temp_f`, `heat_index_f`, or `humidity_pct`.

| Output Column | Data Type | Description |
|---|---|---|
| `point_id`, `lat`, `lon` | `STRING`, `FLOAT64`, `FLOAT64` | Candidate point identifier and coordinates. |
| `geohash_7`, `spatial_block_id` | `STRING` | Geohash-7 (`~150m`) and Geohash-5 (`~4.9km`) spatial block keys. |
| `tract_geoid` | `STRING` | Joined 11-character Census tract FIPS (`ST_INTERSECTS` polygon with nearest-within-2km fallback). |
| `dist_to_city_center_km`, `rel_lat`, `rel_lon` | `FLOAT64` | Pure spatial features relative to Downtown Atlanta (`33.7490, -84.3880`). |
| `pop_density_km2`, `housing_density_km2`, `median_year_built`, `building_age_years`, `water_area_share`, `poverty_rate`, `no_vehicle_rate`, `pct_age_65_plus`, `median_income` | `FLOAT64` | Model-ready physical/built-environment and demographic features from `a4i_ml.tracts_enriched` (`0` nulls, `0` sentinels). |
| `nearest_reading_m` | `FLOAT64` | Distance in meters to the closest Atlanta Heat Watch reading in `a4i_core.heat_readings`. |
| `in_footprint` | `BOOL` | `TRUE` if within 500 m of an Atlanta Heat Watch reading; `FALSE` triggers refusal for out-of-footprint predictions. |
