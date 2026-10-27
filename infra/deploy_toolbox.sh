#!/usr/bin/env bash
# infra/deploy_toolbox.sh
# Store toolbox/tools.yaml in Secret Manager (`heat-toolbox-tools`) and deploy
# the `heat-toolbox` MCP Toolbox service to Cloud Run (Stage 1 / M1).
set -euo pipefail

PROJECT="${GOOGLE_CLOUD_PROJECT:-qwiklabs-gcp-04-ec3596addc43}"
REGION="${COMPUTE_REGION:-us-central1}"
SECRET_NAME="heat-toolbox-tools"
SERVICE_NAME="heat-toolbox"
TOOLBOX_IMAGE="us-central1-docker.pkg.dev/database-toolbox/toolbox/toolbox:0.21.0"
TOOLBOX_SA="toolbox-sa@${PROJECT}.iam.gserviceaccount.com"
AGENT_SA="heat-agent-sa@${PROJECT}.iam.gserviceaccount.com"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "==> [1/4] Syncing toolbox/tools.yaml to Secret Manager (${SECRET_NAME})..."
if ! gcloud secrets describe "${SECRET_NAME}" --project="${PROJECT}" >/dev/null 2>&1; then
  gcloud secrets create "${SECRET_NAME}" \
    --replication-policy="automatic" \
    --labels="team=team,app=heat-planner,env=hackathon" \
    --project="${PROJECT}" \
    --quiet
fi
gcloud secrets versions add "${SECRET_NAME}" \
  --data-file="${REPO_ROOT}/toolbox/tools.yaml" \
  --project="${PROJECT}" \
  --quiet

gcloud secrets add-iam-policy-binding "${SECRET_NAME}" \
  --member="serviceAccount:${TOOLBOX_SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --project="${PROJECT}" \
  --quiet >/dev/null

echo "==> [2/4] Deploying ${SERVICE_NAME} to Cloud Run (${REGION})..."
gcloud run deploy "${SERVICE_NAME}" \
  --image="${TOOLBOX_IMAGE}" \
  --region="${REGION}" \
  --project="${PROJECT}" \
  --service-account="${TOOLBOX_SA}" \
  --network="heat-planner-vpc" \
  --subnet="heat-planner-subnet" \
  --vpc-egress="private-ranges-only" \
  --set-secrets="/config/tools.yaml=${SECRET_NAME}:latest" \
  --args="--tools-file=/config/tools.yaml,--address=0.0.0.0,--port=8080" \
  --port=8080 \
  --cpu=1 \
  --memory=512Mi \
  --min-instances=1 \
  --max-instances=5 \
  --no-allow-unauthenticated \
  --labels="team=team,app=heat-planner,env=hackathon" \
  --quiet

echo "==> [3/4] Granting roles/run.invoker on ${SERVICE_NAME} to ${AGENT_SA} and current caller..."
gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
  --region="${REGION}" \
  --project="${PROJECT}" \
  --member="serviceAccount:${AGENT_SA}" \
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

TOOLBOX_URL="$(gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" --project="${PROJECT}" --format='value(status.url)')"
echo "==> [4/4] ${SERVICE_NAME} deployed at: ${TOOLBOX_URL}"
