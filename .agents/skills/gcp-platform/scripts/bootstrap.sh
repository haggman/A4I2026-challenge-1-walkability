#!/usr/bin/env bash
# bootstrap.sh: one-time, idempotent project setup for the heat planner.
# Usage (Cloud Shell, repo root):  TEAM=myteam bash infra/bootstrap.sh
# Safe to re-run. Creates nothing that already exists; never deletes.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
BQ_LOCATION="${BQ_LOCATION:-US}"
TEAM="${TEAM:?set TEAM=<your-team-slug>}"
LABELS="team=${TEAM},app=heat-planner,env=hackathon"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

[[ -n "$PROJECT_ID" && "$PROJECT_ID" != "(unset)" ]] || { echo "No project set"; exit 1; }
say "Project ${PROJECT_ID} (${PROJECT_NUMBER}) · region ${REGION} · team ${TEAM}"

say "1/5 Enabling APIs (takes a minute the first time)"
gcloud services enable --project "$PROJECT_ID" \
  bigquery.googleapis.com aiplatform.googleapis.com run.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com \
  iam.googleapis.com logging.googleapis.com cloudtrace.googleapis.com \
  storage.googleapis.com geocoding-backend.googleapis.com

say "2/5 Service accounts"
for sa in heat-agent-sa toolbox-sa; do
  if ! gcloud iam service-accounts describe "${sa}@${PROJECT_ID}.iam.gserviceaccount.com" \
        --project "$PROJECT_ID" >/dev/null 2>&1; then
    gcloud iam service-accounts create "$sa" --project "$PROJECT_ID" \
      --display-name "heat planner: ${sa}"
  else
    echo "  ${sa} exists"
  fi
done
AGENT_SA="heat-agent-sa@${PROJECT_ID}.iam.gserviceaccount.com"
TOOLBOX_SA="toolbox-sa@${PROJECT_ID}.iam.gserviceaccount.com"
RE_AGENT="service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"

say "3/5 Project-level roles (add-iam-policy-binding is idempotent)"
bind() { gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="$1" --role="$2" \
           --condition=None --quiet >/dev/null && echo "  $2 → $1"; }
for role in roles/bigquery.jobUser roles/aiplatform.user roles/logging.logWriter roles/cloudtrace.agent; do
  bind "serviceAccount:${AGENT_SA}" "$role"
done
bind "serviceAccount:${TOOLBOX_SA}" roles/bigquery.jobUser
# Agent Runtime's service agent exists only after its first use, so binding fails before that.
bind "serviceAccount:${RE_AGENT}" roles/bigquery.jobUser 2>/dev/null || \
  echo "  (Agent Runtime service agent not created yet; re-run after the first agent_runtime deploy)"

say "4/5 Datasets"
for ds in a4i_climate a4i_ml; do
  if bq --project_id="$PROJECT_ID" show --dataset "${PROJECT_ID}:${ds}" >/dev/null 2>&1; then
    echo "  ${ds} exists"
  else
    bq --project_id="$PROJECT_ID" --location="$BQ_LOCATION" mk --dataset \
       --label=app:heat-planner --label="team:${TEAM}" "${PROJECT_ID}:${ds}"
  fi
done

say "5/5 Dataset-scoped read access (BigQuery DCL)"
for ds in a4i_climate a4i_ml; do
  for sa in "$AGENT_SA" "$TOOLBOX_SA" "$RE_AGENT"; do
    [[ "$sa" == "$RE_AGENT" ]] && ! gcloud projects get-iam-policy "$PROJECT_ID" \
      --format='value(bindings.members)' | grep -q "$RE_AGENT" && continue
    bq --project_id="$PROJECT_ID" --location="$BQ_LOCATION" query --use_legacy_sql=false --quiet \
      "GRANT \`roles/bigquery.dataViewer\` ON SCHEMA \`${PROJECT_ID}.${ds}\` TO \"serviceAccount:${sa}\"" \
      >/dev/null && echo "  dataViewer on ${ds} → ${sa}"
  done
done

say "Done. Next: data lane loads data; then infra/deploy_toolbox.sh and infra/deploy_agent.sh"
