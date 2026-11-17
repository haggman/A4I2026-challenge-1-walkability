#!/usr/bin/env bash
# Builds the a4i_grid tables in dependency order. Safe to re-run: every step is
# CREATE OR REPLACE. Takes about a minute.
#
#   bash sql/grid/build.sh                    # uses gcloud's current project
#   bash sql/grid/build.sh my-project-id      # or name it explicitly
#
# Needs, in the same project:
#   a4i_brooklyn.heat_observations, a4i_brooklyn.station_daily_temps   (load notebook / load.sh)
#   nyc_trees.tree_census_2015      (bq cp bigquery-public-data:new_york_trees.tree_census_2015 ...)
#   the a4i_grid dataset            (bq mk --dataset --location=US <project>:a4i_grid)
set -euo pipefail

PROJECT="${1:-$(gcloud config get-value project 2>/dev/null)}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

STEPS=(
  01_tract_exposure.sql       # impact source: tracts (cars, poverty)
  02_blockgroup_exposure.sql  # impact source: block groups (age, income, rent burden)
  03_cell_readings.sql        # heat: every reading tagged with its cell
  04_cell_heat.sql            # heat: per-cell offset = the training label
  05_city_heat_history.sql    # heat: station history, city-wide
  06_cell_heat_history.sql    # heat: estimated history per cell and year
  07_cells.sql                # base grid
  08_cell_built.sql           # built environment = model features
  09_cell_impact.sql          # who is affected, per cell
  10_views.sql                # training_examples, cell_heat_summary, cell_profile
)

for f in "${STEPS[@]}"; do
  echo "== ${f}"
  bq --project_id="${PROJECT}" query --use_legacy_sql=false --quiet < "${DIR}/${f}"
done
echo "Done: ${PROJECT}.a4i_grid"
