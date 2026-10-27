#!/usr/bin/env bash
# infra/smoke_toolbox.sh
# Smoke test all MCP Toolbox tools on the deployed `heat-toolbox` Cloud Run service (M1).
set -euo pipefail

PROJECT="${GOOGLE_CLOUD_PROJECT:-qwiklabs-gcp-04-ec3596addc43}"
REGION="${COMPUTE_REGION:-us-central1}"
SERVICE_NAME="heat-toolbox"

TOOLBOX_URL="${TOOLBOX_URL:-$(gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" --project="${PROJECT}" --format='value(status.url)')}"
TOKEN="$(gcloud auth print-identity-token)"

echo "==> Testing ${SERVICE_NAME} at ${TOOLBOX_URL}"
echo "1) GET /api/toolset/heat-planner"
curl -fsS -H "Authorization: Bearer ${TOKEN}" "${TOOLBOX_URL}/api/toolset/heat-planner" | head -c 500
echo ""

echo "2) POST /api/tool/explain_point/invoke (Venetian Hills 33.7172, -84.4426)"
curl -fsS -X POST -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  -d '{"lat": 33.7172, "lon": -84.4426}' \
  "${TOOLBOX_URL}/api/tool/explain_point/invoke"
echo ""

echo "3) POST /api/tool/rank_sites_pool/invoke"
curl -fsS -X POST -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  -d '{"unmeasured_only": false, "limit": 5}' \
  "${TOOLBOX_URL}/api/tool/rank_sites_pool/invoke" | head -c 600
echo ""

echo "4) POST /api/tool/equity_audit/invoke"
curl -fsS -X POST -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
  -d '{"geo_id_1": "13121007603", "geo_id_2": "13121004200", "geo_id_3": "13121004800"}' \
  "${TOOLBOX_URL}/api/tool/equity_audit/invoke"
echo ""
echo "==> Smoke test PASSED."
