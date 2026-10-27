# heat-ui (Stage 3)

The planner web UI and its FastAPI backend, per `docs/agents/IMPLEMENTATION_PLAN.md` Stage 3.
Four pages (Ask · Sites · Equity audit · Proposal) drawn from a `VizSpec` that `viz_builder.py`
builds deterministically from heat-planner-api's `AgentApiResponse`. No BigQuery access here.

| File | What it is |
|---|---|
| `contracts/agent_api.py` | What heat-ui reads from heat-planner-api: the shape `_to_api_dict` (`agent/heat_planner/api.py`) serves over HTTP, plus the tract layer. |
| `contracts/viz_spec.py` | `VizSpec` and `FinalResponse` (owned here). `python -m ui_service.export_schemas` writes `docs/contracts/viz_spec.schema.json` and `final_response.schema.json`. |
| `viz_builder.py` | `AgentApiResponse` (+ tract layer) → `VizSpec`. |
| `main.py` | `/api/plan` → heat-planner-api `POST /api/v1/plan` (OIDC as heat-ui-sa); `/api/tracts`; `/api/config`. |
| `mock.py`, `samples/` | Mock agent API serving real heat-planner-api responses (the tract layer is synthetic). Used when `UI_MOCK=1` or `AGENT_API_URL` is unset; every page shows a mock banner. |

## Run locally (mock)

```bash
pip install -r ui_service/requirements.txt
UI_MOCK=1 uvicorn ui_service.main:app --port 8080
```

Open `http://localhost:8080/`, ask "Where should 3 cooling centers go?", then visit each page.

## Test

```bash
pytest ui_service/tests
```

## Agent API endpoints used

- `POST /api/v1/plan` with `{session_id, message}`: answers, shaped for this UI by `_to_api_dict` in `agent/heat_planner/api.py`.
- `GET /api/v1/tracts`: every Atlanta tract for the map and audit scatter (Toolbox tool `tract_layer`, cached an hour).

`samples/` is real `/api/v1/plan` output. After `docs/contracts/samples/` changes, regenerate it from the repo root:

```bash
PYTHONPATH=. python scripts/build_ui_samples.py
```
