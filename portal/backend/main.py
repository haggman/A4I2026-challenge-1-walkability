"""Heat planning portal: FastAPI serving the map data, persona catalogue and the front end.

Run locally from portal/:
    .venv/bin/uvicorn backend.main:app --reload --port 8080
"""
from pathlib import Path
import json
import re
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import data, personas

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="Brooklyn Heat Portal")
app.add_middleware(GZipMiddleware, minimum_size=1024)


class AskRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000, description="The planner's question.")
    persona: Optional[str] = Field(
        default=None, description="The planner role selected in the UI."
    )


class AskLocation(BaseModel):
    rank: int = Field(ge=1, description="Priority order, starting at 1.")
    lat: float = Field(ge=-90, le=90, description="Latitude in decimal degrees (WGS 84).")
    lon: float = Field(ge=-180, le=180, description="Longitude in decimal degrees (WGS 84).")
    label: str = Field(description="Short human-readable name for the location.")
    metric: str = Field(description="Name of the measure used to select or rank this location.")
    value: Optional[float] = Field(
        default=None, description="Value of metric at this location, when available."
    )
    unit: Optional[str] = Field(default=None, description="Unit for value, when available.")
    layer: Optional[str] = Field(
        default=None, description="Map layer identifier associated with this location."
    )
    source: Literal["measured", "estimated", "predicted", "external"] = Field(
        description="Whether this location is based on measured, estimated, predicted, or external data."
    )


class AskResponse(BaseModel):
    mode: Literal["demo", "agent"] = Field(
        description="Whether this response came from the deterministic demo or the connected planning agent."
    )
    reply: str = Field(description="A concise answer to the planner.")
    locations: list[AskLocation] = Field(
        default_factory=list,
        description="Matching locations, ordered by relevance to the question.",
    )
    caveats: list[str] = Field(
        default_factory=list,
        description="Data limitations or qualifications relevant to this answer.",
    )


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


def _ranked_demo_locations(request: AskRequest) -> AskResponse:
    """Return deterministic location results from the local snapshot; no LLM is involved."""
    try:
        snapshot = json.loads(data.cells_json())
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

    text = request.message.lower()
    hottest_place = bool(re.search(r"\b(hottest|warmest|highest temperature)\b", text))
    dispatch_intent = bool(re.search(
        r"\b(deploy|dispatch|deployment|water\s+trucks?|hydration\s+trucks?|cooling\s+trucks?)\b",
        text,
    ))
    elderly = bool(re.search(r"\b(elderly|seniors?|older|65\+|aged|wellness)\b", text))
    no_car = bool(re.search(r"\b(no car|without a car|without cars|car access|households without)\b", text))
    trees = bool(re.search(r"\b(trees?|shade|shaded|canopy)\b", text))
    heat = hottest_place or bool(re.search(
        r"\b(hot\w*|heat|temperature|degrees|dangerous|95|100|102|feels like|heat index|trucks?|hydration)\b",
        text,
    )) or dispatch_intent
    heat_days = bool(re.search(r"\b(days|how often|history|historical)\b", text))

    criteria = []
    if dispatch_intent:
        elderly = True
        no_car = True
    if elderly:
        criteria.append(("est_residents_65_plus", True))
    if no_car:
        criteria.append(("tract_no_vehicle_rate", True))
    if trees:
        criteria.append(("trees_100m", False))
    if heat:
        criteria.append(("est_days_ge_95_per_year" if heat_days else "offset_f", True))
    if not criteria:
        return AskResponse(
            mode="demo",
            reply="I couldn't match that question to a location measure in the demo data.",
            locations=[],
            caveats=["Try asking about heat, older residents, households without cars, trees, or shade."],
        )

    columns = {name: index for index, name in enumerate(snapshot["columns"])}
    missing = [key for key, _ in criteria if key not in columns]
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"The data snapshot is missing required location measures: {', '.join(missing)}.",
        )
    land_index = columns["is_land"]
    candidates = [
        row for row in snapshot["rows"]
        if row[land_index] and all(isinstance(row[columns[key]], (int, float)) for key, _ in criteria)
    ]
    if not candidates:
        return AskResponse(
            mode="demo",
            reply="There are no locations with all requested measures in the current snapshot.",
            locations=[],
            caveats=["The demo can only map cells with available data for every requested measure."],
        )

    ranked_criteria = []
    for key, descending in criteria:
        ordered = sorted(candidates, key=lambda row: row[columns[key]], reverse=descending)
        ranks = {
            id(row): 1 - index / max(1, len(ordered) - 1)
            for index, row in enumerate(ordered)
        }
        ranked_criteria.append((key, ranks))

    ranked_rows = sorted(
        (
            (
                sum(ranks[id(row)] for _, ranks in ranked_criteria) / len(ranked_criteria),
                row,
            )
            for row in candidates
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    single_location = hottest_place and not dispatch_intent and not bool(
        re.search(r"\b(places|locations|spots|areas)\b", text)
    )
    limit = 1 if single_location else 10
    locations = []
    for rank, (_, row) in enumerate(ranked_rows[:limit], start=1):
        values = {key: row[index] for key, index in columns.items()}
        primary_key = next(
            (key for key, _ in criteria if key in ("offset_f", "est_days_ge_95_per_year")),
            criteria[0][0],
        )
        value = values[primary_key]
        unit = {
            "offset_f": "°F versus campaign average",
            "est_days_ge_95_per_year": "estimated days/year",
            "est_residents_65_plus": "estimated residents",
            "tract_no_vehicle_rate": "share",
            "trees_100m": "trees within 100 m",
        }.get(primary_key)
        source = (
            "measured" if primary_key == "offset_f"
            else "estimated" if primary_key.startswith("est_")
            else "external"
        )
        locations.append(AskLocation(
            rank=rank,
            lat=(values["cell_i"] + 0.5) * snapshot["cell_deg"],
            lon=(values["cell_j"] + 0.5) * snapshot["cell_deg"],
            label=f"Brooklyn grid cell ({values['cell_i']}, {values['cell_j']})",
            metric=primary_key,
            value=value,
            unit=unit,
            layer=primary_key,
            source=source,
        ))

    metric_names = [key for key, _ in criteria]
    primary_metric = next(
        (key for key in metric_names if key in ("offset_f", "est_days_ge_95_per_year")),
        metric_names[0],
    )
    if dispatch_intent:
        reply = (
            f"Here are {len(locations)} candidate water-truck deployment cells, ranked by "
            "measured campaign heat and available older-resident and no-car indicators."
        )
    elif hottest_place and len(criteria) == 1 and criteria[0][0] == "offset_f":
        reply = "The warmest measured block in the available campaign snapshot is highlighted."
    else:
        reply = f"Here are {len(locations)} matching locations ranked using the requested measures in the available map data."
    caveats = [
        "Demo response generated deterministically by the backend from its local data snapshot; no AI agent was used.",
    ]
    if primary_metric == "offset_f":
        caveats.append(
            "Heat values are relative to the campaign average and measured on one campaign afternoon; they are not today's temperatures."
        )
    if dispatch_intent:
        caveats.append(
            "This is not a forecast for tomorrow or a truck-routing plan. Locations are grid cells, not verified legal or safe stopping sites; confirm current conditions, access, and operational constraints before dispatch."
        )
    if len(criteria) > 1:
        caveats.append("Multiple measures are combined by their relative rank, not by a trained recommendation model.")
    return AskResponse(mode="demo", reply=reply, locations=locations, caveats=caveats)


@app.post(
    "/api/ask",
    response_model=AskResponse,
    responses={503: {"description": "Required snapshot data is unavailable."}},
)
def ask(request: AskRequest):
    """Demo backend returning structured, mappable locations from the local snapshot."""
    return _ranked_demo_locations(request)


app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
