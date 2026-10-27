#!/usr/bin/env bash
# infra/iam_bootstrap.sh
# Idempotent Service Account & least-privilege IAM + BigQuery dataset grant bootstrap
# for Stage 1 (M1) of the Atlanta Urban Heat Planning Assistant.
set -euo pipefail

PROJECT="${GOOGLE_CLOUD_PROJECT:-qwiklabs-gcp-04-ec3596addc43}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ensure_sa() {
  local sa_name="$1"
  local display_name="$2"
  local sa_email="${sa_name}@${PROJECT}.iam.gserviceaccount.com"
  if ! gcloud iam service-accounts describe "${sa_email}" --project="${PROJECT}" >/dev/null 2>&1; then
    gcloud iam service-accounts create "${sa_name}" \
      --display-name="${display_name}" \
      --project="${PROJECT}" \
      --quiet
  fi
}

echo "==> [1/3] Ensuring dedicated Service Accounts (toolbox-sa, heat-agent-sa, heat-ui-sa)..."
ensure_sa "toolbox-sa" "MCP Toolbox BigQuery Service Account"
ensure_sa "heat-agent-sa" "Heat Planner ADK Agent API Service Account"
ensure_sa "heat-ui-sa" "Heat Planner UI Service Account"

TOOLBOX_SA="toolbox-sa@${PROJECT}.iam.gserviceaccount.com"
AGENT_SA="heat-agent-sa@${PROJECT}.iam.gserviceaccount.com"
UI_SA="heat-ui-sa@${PROJECT}.iam.gserviceaccount.com"

echo "==> [2/3] Granting project-level runtime roles..."
for role in roles/bigquery.jobUser roles/secretmanager.secretAccessor roles/cloudtrace.agent; do
  gcloud projects add-iam-policy-binding "${PROJECT}" \
    --member="serviceAccount:${TOOLBOX_SA}" \
    --role="${role}" --condition=None --quiet >/dev/null
done

for role in roles/bigquery.jobUser roles/aiplatform.user roles/secretmanager.secretAccessor roles/cloudtrace.agent; do
  gcloud projects add-iam-policy-binding "${PROJECT}" \
    --member="serviceAccount:${AGENT_SA}" \
    --role="${role}" --condition=None --quiet >/dev/null
done

for role in roles/secretmanager.secretAccessor roles/cloudtrace.agent; do
  gcloud projects add-iam-policy-binding "${PROJECT}" \
    --member="serviceAccount:${UI_SA}" \
    --role="${role}" --condition=None --quiet >/dev/null
done

echo "==> [3/3] Applying dataset-level BigQuery roles/bigquery.dataViewer on a4i_core, a4i_semantic, a4i_ml..."
bq query --project_id="${PROJECT}" --location=US --use_legacy_sql=false < "${REPO_ROOT}/sql/grants/01_grant_dataviewer.sql"
echo "IAM & dataset bootstrap complete."
