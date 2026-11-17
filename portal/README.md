# Brooklyn Heat Portal

A planner-facing front end for the heat assistant. It starts with a **map view** that overlays
every feature in the `a4i_grid` dataset on Brooklyn, plus one view per decision from the team's
planning sheet (Today, Decade, Equity audit, Heat history, Ask the agent).

Each view lists the persona questions it will answer and how far the data gets us today:
**Ready now**, **Needs model**, **Needs agent**, or **Needs external data**. That catalogue
lives in [`backend/personas.py`](backend/personas.py). Update a status there when the model, the
agent or a dataset lands.

## Run it locally

```bash
cd portal
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r pyproject.toml
.venv/bin/python -m backend.data refresh      # BigQuery -> data/ snapshot (~10 s)
.venv/bin/uvicorn backend.main:app --reload --port 8080
```

Open http://localhost:8080.

`refresh` uses your **gcloud CLI** login (`gcloud auth print-access-token`), not
application-default credentials, because ADC is often a different Google account than the
Qwiklabs one. Set `GCP_PROJECT` if your project isn't `qwiklabs-gcp-03-941c9ce79592`.

Re-run `refresh` whenever `sql/grid/build.sh` rebuilds the tables.

## What's where

| Path | What it does |
|---|---|
| `backend/main.py` | FastAPI endpoints, including `/api/ask` demo location search, and serves `frontend/` |
| `backend/data.py` | BigQuery → compact JSON snapshot in `data/` (git-ignored) |
| `backend/personas.py` | Views and the 20 persona questions, each with a data-readiness status |
| `frontend/js/layers.js` | Map layer catalogue: label, palette, scale, notes. **Add a feature here** |
| `frontend/js/map.js` | MapLibre map: cells, tracts, overlays, legend, inspector |
| `frontend/js/views.js` | The non-map views, generated from the persona catalogue |

No front-end build step: plain ES modules plus MapLibre GL from a CDN.

## Ask API contract

The backend publishes the request and response schemas for `POST /api/ask` in
[FastAPI's OpenAPI docs](http://localhost:8080/docs) and `/openapi.json`.

Request:

```json
{
  "message": "Where are the hottest measured blocks?",
  "persona": "Emergency manager"
}
```

Successful response:

```json
{
  "mode": "demo",
  "reply": "The warmest measured block in the available campaign snapshot is highlighted.",
  "locations": [
    {
      "lat": 40.6445,
      "lon": -73.9675,
      "rank": 1,
      "label": "Brooklyn grid cell (40644, -73968)",
      "metric": "offset_f",
      "value": 4.2,
      "unit": "°F versus campaign average",
      "layer": "offset_f",
      "source": "measured"
    }
  ],
  "caveats": [
    "Measurements are from one campaign afternoon and are relative to the campaign average, not today's air temperature."
  ]
}
```

Return locations in relevance order. Use decimal WGS 84 coordinates; `source` must be
`measured`, `estimated`, `predicted`, or `external`. Return an empty `locations` array when
the answer does not identify places, and include limitations in `caveats`. The endpoint
currently returns deterministic `mode: "demo"` results ranked from the local data snapshot;
it does not call an AI agent. The map chat sends its message and selected persona to this
endpoint, then maps the returned coordinates.

Water-truck deployment questions return up to ten ranked candidate grid cells. The map
highlights each cell and numbers its marker to match the ranked chat results. The demo ranks
these candidates using measured campaign heat plus estimated older-resident and no-car
indicators. It does not forecast tomorrow's heat or identify verified stopping locations.

## Design decisions to defend

- **Basemap: USGS The National Map**, which is US Government work in the public domain.
  OpenStreetMap-based tiles would raise the ODbL share-alike question the challenge README warns about.
- **Cells are drawn in the browser** from `(cell_i, cell_j)` — the same 0.001° grid as the SQL —
  so the payload stays ~3 MB raw (much smaller gzipped) for 29.5k cells.
- **Demographics are shown on tracts, not cells.** They are not model inputs; the legend group says so.
- **Snapshot, not live queries.** The demo doesn't depend on BigQuery latency, and the front-end
  lane can work without credentials.

## Adding a layer

1. Add the column to `CELL_COLUMNS` or `TRACT_COLUMNS` in `backend/data.py`.
2. `python -m backend.data refresh`
3. Add an entry to `LAYER_GROUPS` in `frontend/js/layers.js`.

When the model is trained, export `predicted_offset` (and the top attributions) per cell, and
flip the `predicted_offset` layer's `status` to `ready`.

## Deploy to Cloud Run

```bash
cd portal
gcloud run deploy heat-portal --source . --region us-central1 --min-instances 1 --allow-unauthenticated
```

The `data/` snapshot is uploaded with the source (see `.gcloudignore`). If it's missing, the
first request builds it from BigQuery with the service account, which needs BigQuery Data
Viewer and Job User roles. `--min-instances 1` avoids a cold start during the demo.
