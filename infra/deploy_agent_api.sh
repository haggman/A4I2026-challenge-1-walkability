#!/usr/bin/env bash
# infra/deploy_agent_api.sh
# Deploy `heat-planner-api` (Stage 2 / M4) to its own Cloud Run service attached to
# `heat-planner-vpc` and connected to `heat-toolbox`.
set -euo pipefail

PROJECT="${GOOGLE_CLOUD_PROJECT:-qwiklabs-gcp-04-ec3596addc43}"
REGION="${COMPUTE_REGION:-us-central1}"
SERVICE_NAME="heat-planner-api"
AGENT_SA="heat-agent-sa@${PROJECT}.iam.gserviceaccount.com"
UI_SA="heat-ui-sa@${PROJECT}.iam.gserviceaccount.com"

TOOLBOX_URL="${TOOLBOX_URL:-$(gcloud run services describe heat-toolbox --region="${REGION}" --project="${PROJECT}" --format='value(status.url)')}"

echo "==> Deploying ${SERVICE_NAME} to Cloud Run (${REGION}) with TOOLBOX_URL=${TOOLBOX_URL}..."
gcloud run deploy "${SERVICE_NAME}" \
  --source="." \
  --region="${REGION}" \
  --project="${PROJECT}" \
  --service-account="${AGENT_SA}" \
  --network="heat-planner-vpc" \
  --subnet="heat-planner-subnet" \
  --vpc-egress="private-ranges-only" \
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=1,GOOGLE_CLOUD_PROJECT=${PROJECT},GOOGLE_CLOUD_LOCATION=global,COMPUTE_REGION=${REGION},BQ_LOCATION=US,CITY=Atlanta,TRACK=budget,SCENARIO_SITES=3,BQML_MODEL_ID=offset_model_v1,AGENT_MODEL=gemini-3-flash-preview,WRITER_MODEL=gemini-3-flash-preview,TOOLBOX_URL=${TOOLBOX_URL},TOOLBOX_TOOLSET=heat-planner" \
  --port=8000 \
  --cpu=2 \
  --memory=1Gi \
  --min-instances=1 \
  --max-instances=5 \
  --no-allow-unauthenticated \
  --labels="team=team,app=heat-planner,env=hackathon" \
  --quiet

echo "==> Granting roles/run.invoker on ${SERVICE_NAME} to ${UI_SA} and current caller..."
gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT}" \
  --member="serviceAccount:${UI_SA}" \
  --role="roles/run.invoker" \
  --quiet >/dev/null

ACTIVE_USER="$(gcloud config get-value account 2>/dev/null || true)"
if [[ -n "${ACTIVE_USER}" ]]; then
  gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
    --region="${REGION}" \
    --project="${PROJECT}" \
    --member="user:${ACTIVE_USER}" \
    --role="roles/run.invoker" \
    --quiet >/dev/null || true
fi

AGENT_API_URL="$(gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" --project="${PROJECT}" --format='value(status.url)')"
echo "==> ${SERVICE_NAME} deployed at: ${AGENT_API_URL}"
