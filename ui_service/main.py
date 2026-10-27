"""heat-ui: the planner web UI and its FastAPI backend (IMPLEMENTATION_PLAN.md Stage 3).

  /                 the planner (static files in static/)
  POST /api/plan    forwards to heat-planner-api POST /api/v1/plan, returns FinalResponse
  GET  /api/tracts  tract layer for the map and audit scatter (heat-planner-api /api/v1/tracts)
  GET  /api/config  city, Maps browser key, mock flag

No BigQuery access here: all data comes from heat-planner-api. With UI_MOCK=1, or with no
AGENT_API_URL, answers come from samples/ instead.
"""

import os
import time
import uuid

import requests
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from . import mock
from .contracts.agent_api import AgentApiResponse, PlanRequest, TractLayer
from .contracts.viz_spec import FinalResponse
from .viz_builder import build_viz_spec

AGENT_API_URL = os.getenv("AGENT_API_URL", "").rstrip("/")
MOCK = os.getenv("UI_MOCK", "0") == "1" or not AGENT_API_URL
CITY = os.getenv("CITY_NAME", "Atlanta")
TIMEOUT_S = float(os.getenv("AGENT_TIMEOUT_S", "30"))
TRACTS_TTL_S = 3600
AVAILABLE_CITIES = [
    ("Seattle", "Contrast city, stretch goal (~35k readings)"),
    ("Dallas", "~19k readings"),
    ("Houston", "~147k readings"),
    ("Chicago", "~49k readings"),
    ("Los Angeles (Central)", "~17k readings"),
    ("New York (Brooklyn)", "~15k readings"),
    ("New York (Manhattan/Bronx)", "~12k readings"),
]

app = FastAPI(title="heat-ui")
_tracts: tuple[float, TractLayer] | None = None


def _auth_headers() -> dict[str, str]:
    """OIDC identity token for heat-ui-sa (roles/run.invoker on heat-planner-api)."""
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token

    return {"Authorization": f"Bearer {id_token.fetch_id_token(Request(), AGENT_API_URL)}"}


def _agent(method: str, path: str, **kw) -> dict:
    try:
        r = requests.request(method, f"{AGENT_API_URL}{path}", headers=_auth_headers(), timeout=TIMEOUT_S, **kw)
    except requests.RequestException as e:
        raise HTTPException(502, f"Couldn't reach the agent API: {e}") from e
    if r.status_code >= 400:
        raise HTTPException(502, f"Agent API returned {r.status_code}: {r.text[:300]}")
    return r.json()


def tracts() -> TractLayer | None:
    global _tracts
    if MOCK:
        return mock.tract_layer()
    if _tracts and time.time() - _tracts[0] < TRACTS_TTL_S:
        return _tracts[1]
    try:
        layer = TractLayer.model_validate(_agent("GET", "/api/v1/tracts"))
    except HTTPException:
        return None  # the agent API may not offer the tract layer yet; map falls back to pins only
    _tracts = (time.time(), layer)
    return layer


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"ok": True, "mock": MOCK}


@app.get("/api/config")
def config():
    return {
        "city": CITY,
        "mock": MOCK,
        "mapsKey": os.getenv("MAPS_BROWSER_KEY", ""),
        "sessionId": f"ui-{uuid.uuid4().hex[:12]}",
        "availableCities": [{"name": n, "note": note} for n, note in AVAILABLE_CITIES],
    }


@app.get("/api/tracts")
def get_tracts():
    layer = tracts()
    if layer is None:
        raise HTTPException(503, "The agent API doesn't serve the tract layer yet.")
    return layer.model_dump(mode="json")


@app.post("/api/plan", response_model=FinalResponse, response_model_by_alias=True)
def plan(req: PlanRequest) -> FinalResponse:
    if MOCK:
        resp = mock.plan(req.message)
    else:
        resp = AgentApiResponse.model_validate(_agent("POST", "/api/v1/plan", json=req.model_dump()))
    viz = build_viz_spec(resp, tracts(), mock=MOCK)
    return FinalResponse(**resp.model_dump(), viz_spec=viz)


app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static"), html=True), name="ui")
