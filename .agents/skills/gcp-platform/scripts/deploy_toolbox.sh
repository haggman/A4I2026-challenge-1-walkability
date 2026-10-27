#!/usr/bin/env bash
# deploy_toolbox.sh: MCP Toolbox for Databases on Cloud Run: private, warm, pinned.
# Usage: TOOLBOX_VERSION=<x.y.z> bash infra/deploy_toolbox.sh   (tools file: toolbox/tools.yaml)
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
TEAM="${TEAM:-team}"
TOOLBOX_VERSION="${TOOLBOX_VERSION:?pin it: see github.com/googleapis/mcp-toolbox/releases}"
IMAGE="us-central1-docker.pkg.dev/database-toolbox/toolbox/toolbox:${TOOLBOX_VERSION}"
SERVICE="heat-toolbox"
SECRET="heat-toolbox-tools"
TOOLS_FILE="${TOOLS_FILE:-toolbox/tools.yaml}"
TOOLBOX_SA="toolbox-sa@${PROJECT_ID}.iam.gserviceaccount.com"
AGENT_SA="heat-agent-sa@${PROJECT_ID}.iam.gserviceaccount.com"

[[ -f "$TOOLS_FILE" ]] || { echo "Missing $TOOLS_FILE"; exit 1; }
# Render the PROJECT placeholder into a temp copy; the tracked file stays generic.
RENDERED="$(mktemp)"; trap 'rm -f "$RENDERED"' EXIT
sed "s/PROJECT/${PROJECT_ID}/g" "$TOOLS_FILE" > "$RENDERED"

echo "Secret ${SECRET}: new version from ${TOOLS_FILE} (rendered)"
gcloud secrets describe "$SECRET" --project "$PROJECT_ID" >/dev/null 2>&1 || \
  gcloud secrets create "$SECRET" --project "$PROJECT_ID" --replication-policy=automatic \
    --labels="team=${TEAM},app=heat-planner"
VERSION="$(gcloud secrets versions add "$SECRET" --project "$PROJECT_ID" \
             --data-file="$RENDERED" --format='value(name)' | awk -F/ '{print $NF}')"
gcloud secrets add-iam-policy-binding "$SECRET" --project "$PROJECT_ID" \
  --member="serviceAccount:${TOOLBOX_SA}" --role=roles/secretmanager.secretAccessor --quiet >/dev/null

echo "Deploying ${SERVICE} (${IMAGE}), secret version ${VERSION}"
gcloud run deploy "$SERVICE" --project "$PROJECT_ID" --region "$REGION" \
  --image "$IMAGE" \
  --service-account "$TOOLBOX_SA" \
  --set-secrets "/app/tools.yaml=${SECRET}:${VERSION}" \
  --args="--tools-file=/app/tools.yaml,--address=0.0.0.0,--port=8080" \
  --no-allow-unauthenticated \
  --min-instances=1 --cpu-boost --memory=512Mi --timeout=300 \
  --labels="team=${TEAM},app=heat-planner,env=hackathon" \
  --quiet

gcloud run services add-iam-policy-binding "$SERVICE" --project "$PROJECT_ID" --region "$REGION" \
  --member="serviceAccount:${AGENT_SA}" --role=roles/run.invoker --quiet >/dev/null

URL="$(gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --format='value(status.url)')"
echo "Smoke test:"
curl -fsS -H "Authorization: Bearer $(gcloud auth print-identity-token)" "${URL}/api/toolset/heat-planner" | head -c 400; echo
echo
echo "TOOLBOX_URL=${URL}    ← put this in the agent's env"
