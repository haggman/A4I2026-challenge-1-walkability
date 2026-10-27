#!/usr/bin/env bash
# smoke.sh: ask the DEPLOYED agent two planner questions via the ADK API server (Cloud Run target).
# Usage: AGENT_URL=https://heat-planner-xxxx.run.app bash infra/smoke.sh
set -euo pipefail
AGENT_URL="${AGENT_URL:?set AGENT_URL}"
APP="heat_planner"; USER_ID="smoke"; SID="smoke-$(date +%s)"
AUTH=()
# If the service is private, send an identity token; harmless if public.
TOKEN="$(gcloud auth print-identity-token 2>/dev/null || true)"
[[ -n "$TOKEN" ]] && AUTH=(-H "Authorization: Bearer ${TOKEN}")

curl -fsS "${AUTH[@]}" -X POST "${AGENT_URL}/apps/${APP}/users/${USER_ID}/sessions/${SID}" \
  -H 'Content-Type: application/json' -d '{}' >/dev/null

ask() {
  echo "Q: $1"
  curl -fsS "${AUTH[@]}" -X POST "${AGENT_URL}/run" -H 'Content-Type: application/json' -d @- <<JSON \
  | python3 -c 'import sys,json; ev=json.load(sys.stdin); calls=[p["functionCall"]["name"] for e in ev for p in e.get("content",{}).get("parts",[]) if "functionCall" in p]; text=[p["text"] for e in ev for p in e.get("content",{}).get("parts",[]) if "text" in p]; print("  tools:", calls); print("  answer:", (text[-1] if text else "<none>")[:400])'
{"app_name":"${APP}","user_id":"${USER_ID}","session_id":"${SID}",
 "new_message":{"role":"user","parts":[{"text":"$1"}]}}
JSON
}
ask "We can fund three cooling centers. Where should they go?"
ask "How often does the city hit 100F?"
echo "OK: inspect that tools include rank_candidate_sites and get_heat_frequency."
