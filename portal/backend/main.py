"""Heat planning portal: FastAPI serving the map data, persona catalogue and the front end.

Run locally from portal/:
    .venv/bin/uvicorn backend.main:app --reload --port 8080
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from . import data, personas

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="Brooklyn Heat Portal")
app.add_middleware(GZipMiddleware, minimum_size=1024)


def _json(payload_fn):
    try:
        return Response(payload_fn(), media_type="application/json",
                        headers={"Cache-Control": "no-cache"})
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/cells")
def cells():
    """Every grid cell, columnar: {cell_deg, columns, rows}. The browser builds the squares."""
    return _json(data.cells_json)


@app.get("/api/tracts")
def tracts():
    """Tracts the grid touches, as GeoJSON with cleaned demographics."""
    return _json(data.tracts_json)


@app.get("/api/heat-days")
def heat_days():
    return _json(data.heat_days_json)


@app.get("/api/personas")
def get_personas():
    return {"views": personas.VIEWS, "questions": personas.QUESTIONS}


@app.post("/api/ask")
def ask():
    # Placeholder for the ADK agent. When it's deployed (Agent Runtime or Cloud Run), proxy
    # the planner's message here and stream the reply back to the "Ask the agent" view.
    raise HTTPException(status_code=501, detail="Agent not connected yet.")


app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
