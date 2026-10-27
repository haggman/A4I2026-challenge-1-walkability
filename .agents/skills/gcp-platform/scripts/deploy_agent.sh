#!/usr/bin/env bash
# deploy_agent.sh: deploy agent/heat_planner to Cloud Run (default) or Agent Runtime.
# Usage: TARGET=cloud_run bash infra/deploy_agent.sh
#        TARGET=agent_runtime bash infra/deploy_agent.sh
# Verify flags with `adk deploy <target> --help` on the PINNED ADK version first.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
TEAM="${TEAM:-team}"
TARGET="${TARGET:-cloud_run}"
SERVICE="heat-planner"
AGENT_DIR="agent/heat_planner"
AGENT_SA="heat-agent-sa@${PROJECT_ID}.iam.gserviceaccount.com"
ENV_FILE="${AGENT_DIR}/.env"

[[ -f "$ENV_FILE" ]] || { echo "Missing ${ENV_FILE} (copy .env.example and fill it)"; exit 1; }
grep -qE '^AGENT_MODEL=.+' "$ENV_FILE" || { echo "AGENT_MODEL is empty in ${ENV_FILE}"; exit 1; }
if grep -qE '^MAPS_API_KEY=.+' "$ENV_FILE"; then
  echo "Refusing: MAPS_API_KEY is in ${ENV_FILE}. Put it in Secret Manager instead."; exit 1
fi

echo "Pre-deploy gate: unit tests"
( cd agent && python -m pytest -q -m "not live" tests ) || { echo "Tests failed; not deploying."; exit 1; }

case "$TARGET" in
  cloud_run)
    adk deploy cloud_run \
      --project "$PROJECT_ID" --region "$REGION" \
      --service_name "$SERVICE" \
      --with_ui --trace_to_cloud \
      "$AGENT_DIR"
    # Harden what adk created: own SA, warm instance, env from .env, labels.
    # Strip comments (whole-line and inline) and blank/empty-valued lines; join as K=V,K=V
    ENV_VARS="$(sed -E 's/[[:space:]]*#.*$//' "$ENV_FILE" | grep -E '^[A-Z_]+=.+' | paste -sd, -)"
    gcloud run services update "$SERVICE" --project "$PROJECT_ID" --region "$REGION" \
      --service-account "$AGENT_SA" \
      --update-env-vars "$ENV_VARS" \
      --min-instances=1 --cpu-boost --timeout=300 \
      --labels="team=${TEAM},app=heat-planner,env=hackathon" --quiet
    if gcloud secrets describe maps-api-key --project "$PROJECT_ID" >/dev/null 2>&1; then
      gcloud run services update "$SERVICE" --project "$PROJECT_ID" --region "$REGION" \
        --update-secrets "MAPS_API_KEY=maps-api-key:latest" --quiet
    fi
    URL="$(gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --format='value(status.url)')"
    echo "Agent URL: ${URL}"
    ;;
  agent_runtime)
    BUCKET="gs://${PROJECT_ID}-heat-staging"
    gcloud storage buckets describe "$BUCKET" >/dev/null 2>&1 || \
      gcloud storage buckets create "$BUCKET" --project "$PROJECT_ID" --location "$REGION" \
        --uniform-bucket-level-access
    # Older ADK: `adk deploy agent_engine`. Check --help for the current subcommand name.
    adk deploy agent_engine \
      --project "$PROJECT_ID" --region "$REGION" \
      --staging_bucket "$BUCKET" \
      --display_name "$SERVICE" \
      --trace_to_cloud \
      "$AGENT_DIR"
    echo "Now grant the Agent Runtime service agent BigQuery access: re-run infra/bootstrap.sh"
    ;;
  *) echo "TARGET must be cloud_run or agent_runtime"; exit 1 ;;
esac
