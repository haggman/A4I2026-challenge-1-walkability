#!/usr/bin/env bash
# Trains, evaluates and applies the heat-offset model. Run after sql/grid/build.sh.
# Safe to re-run (everything is CREATE OR REPLACE). Takes about a minute.
#
#   bash sql/model/run.sh [project-id]
set -euo pipefail

PROJECT="${1:-$(gcloud config get-value project 2>/dev/null)}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for f in 01_model_input.sql 02_train.sql 03_evaluate.sql 04_predict.sql 05_history.sql; do
  echo "== ${f}"
  bq --project_id="${PROJECT}" query --use_legacy_sql=false --quiet < "${DIR}/${f}"
done

echo
echo "Held-out evaluation:"
bq --project_id="${PROJECT}" query --use_legacy_sql=false --format=pretty \
  "SELECT holdout_cells, ROUND(holdout_mae_f, 3) AS mae_f, ROUND(holdout_r2, 3) AS r2,
          ROUND(baseline_mae_f, 3) AS baseline_mae_f,
          ROUND(100 * mae_reduction_vs_baseline, 1) AS pct_better_than_baseline
   FROM a4i_grid.model_evaluation"
