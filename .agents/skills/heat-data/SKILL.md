---
name: heat-data
description: Loads, validates and explores the A4I urban-heat BigQuery tables (heat_observations, station_daily_temps, tract_demographics) in dataset a4i_climate. Use when loading a city, checking table health, writing exploratory SQL, computing the per-location heat offset, running the GHCN heat-frequency analysis, or bringing in extra data and checking its license.
---

# Heat data: load, validate, explore

You are acting as the **data engineer** on the data lane. Your job is to produce tables the
model and the agent can trust, and to *prove* they are trustworthy with numbers.

## 1. Load (pick one path; both reach the same end state)

**Preferred:** Colab Enterprise notebook `notebooks/c1_01_load_explore.ipynb`, with `CITY` set at the top.

**Headless fallback** (Cloud Shell, repo root):
```bash
gcloud config set project "$PROJECT_ID"
bash scripts/load.sh --list          # cities in the snapshot
bash scripts/load.sh dallas          # idempotent: every table is WRITE_TRUNCATE
```
Always invoke with `bash`, not `./`. The script verifies row counts and prints the intra-city
spread. Paste that output into `docs/DECISIONS.md`.

Only one person loads. Loading twice concurrently is safe (replace semantics) but wasteful.

## 2. Validate (the tables, not the dataframe)

Run `resources/validate.sql` (substitute the project). Every check must pass before the model
lane trains. Report the result table verbatim. Expected:

| Check | Pass condition |
|---|---|
| heat rows | > 1,000 |
| temp range | 40–140 °F, no sentinel survivors (min > -100) |
| humidity | 0–100 or NULL |
| intra-city spread | > 3 °F (typically 10–20 °F, which is the whole challenge) |
| distinct points | > 500 |
| stations | ≥ 1, multi-year, nearest < 40 km from traverse centroid |
| tracts | > 0, `LENGTH(geo_id)=11`, poverty_rate ∈ [0,1], coords present |

`observed_at` 100% NULL is **expected** for many cities. Do not "fix" it.

## 3. The label: offset from the campaign mean

```sql
SELECT latitude, longitude,
       temp_f - AVG(temp_f) OVER () AS offset_f
FROM `PROJECT.a4i_climate.heat_observations`
```
It's the campaign mean, not a station anchor, because the campaign has no reliable date/time
for many cities. All readings share one one-hour window, so differences are purely spatial.

## 4. Heat frequency (GHCN: "how often?")

`resources/heat_frequency.sql` gives, per year: days ≥ 90/95/100 °F (averaged across stations,
or from the nearest long-record station), plus an OLS slope of days≥95 per year.

Say the honest caveat when reporting a trend: 7 years is **weather variability, not a
climate trend**. Report counts confidently and slopes cautiously.

## 5. Exploration queries worth having ready

- Hottest 15 points and their offset (notebook §7).
- Offset by tract: join each reading to its nearest tract centroid (see
  `resources/nearest_tract.sql`) → mean offset, n readings, population, no_vehicle_rate.
- Coverage map: which tracts have **zero** readings? These are exactly where the model earns
  its keep, and the demo should show one.

## 6. Bringing your own data (augment, don't replace)

Only after the core model is training. For every dataset, record in `docs/DECISIONS.md`:
source URL, license, why this source, join key, row count before/after join.

| License | OK? |
|---|---|
| Public domain, CC0, US Government work | ✅ |
| CC BY | ✅ with attribution (confirm with a coach) |
| NC, ND, CC BY-SA, **ODbL (anything OpenStreetMap)**, unstated | ❌ |

High-value additions by track (see challenge README "What would unlock what"):
- EPA Smart Location DB (CC0): `NatWalkInd`, intersection density, land-use mix. Block-group level.
  `D4A_Ranked` is **non-linear** (1 = no transit, then 13–20), so treat it as categorical.
- NYC only: `bigquery-public-data.new_york_trees.tree_census_2015` → canopy proxy.
- City open-data: cooling centers, libraries/rec centers with hours, tree inventory, impervious surface.

Load extra data into a **separate** dataset `a4i_extra` so `load.sh` re-runs never clobber it.

## 7. Hand-off contract to the agent lane

When validation passes, post in the team channel and in `docs/HANDOFF.md`:
project, dataset, table row counts, spread, city bbox (`MIN/MAX lat/lon`), and timestamp coverage %.

## Diagnostics

If anything looks wrong, run the notebook's final diagnostic cell and paste its block.
Common faults: wrong project in `gcloud config`; dataset exists in another location; empty ACS join (missing `LPAD`).
