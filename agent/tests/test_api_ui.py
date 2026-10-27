"""heat-ui-facing API: GET /api/v1/tracts and the _to_api_dict adapter."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from agent.heat_planner import api
from agent.heat_planner.schemas import AgentApiResponse

SAMPLES = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "samples"
SQUARE = {"type": "Polygon", "coordinates": [[[-84.4, 33.7], [-84.39, 33.7], [-84.39, 33.71], [-84.4, 33.7]]]}


def _rows():
    return [
        {"geo_id": "13121007603", "predicted_offset_f": 1.28, "no_vehicle_rate": 0.5637, "share_65_plus": 0.151,
         "poverty_rate": 0.47, "population": 2775, "geometry_json": json.dumps(SQUARE)},
        {"geo_id": "13121004200", "predicted_offset_f": None, "no_vehicle_rate": 0.467, "share_65_plus": 0.168,
         "poverty_rate": 0.43, "population": None, "geometry_json": json.dumps(SQUARE)},
        {"geo_id": "13121009999", "geometry_json": None},  # no shape: skipped
    ]


def test_tracts_endpoint_returns_feature_collection_and_caches(monkeypatch):
    calls = []

    def fake_invoke(name, *, tool_name, provenance_list=None, **params):
        calls.append((name, params))
        return _rows(), None

    monkeypatch.setattr(api, "invoke_mcp_tool", fake_invoke)
    monkeypatch.setattr(api, "_tract_cache", None)
    client = TestClient(api.app)

    first = client.get("/api/v1/tracts")
    second = client.get("/api/v1/tracts")

    assert first.status_code == 200 and second.json() == first.json()
    assert calls == [("tract_layer", {"simplify_m": api.TRACT_SIMPLIFY_M})]  # second call served from cache
    body = first.json()
    assert body["type"] == "FeatureCollection" and len(body["features"]) == 2
    f = body["features"][0]
    assert f["geometry"]["type"] == "Polygon"
    assert f["properties"] == {"geo_id": "13121007603", "predicted_offset_f": 1.28, "no_vehicle_rate": 0.5637,
                               "share_65_plus": 0.151, "poverty_rate": 0.47, "population": 2775}
    assert body["features"][1]["properties"]["population"] is None


def test_tracts_endpoint_503_when_empty(monkeypatch):
    monkeypatch.setattr(api, "invoke_mcp_tool", lambda *a, **k: ([], None))
    monkeypatch.setattr(api, "_tract_cache", None)
    assert TestClient(api.app).get("/api/v1/tracts").status_code == 503


def test_adapter_maps_prefixed_audit_metrics_and_posthoc_race():
    resp = AgentApiResponse.model_validate(json.loads((SAMPLES / "site_selection_atlanta.json").read_text(encoding="utf-8")))
    ea = api._to_api_dict(resp)["recommendation"]["equity_audit"]

    assert {m["measure"] for m in ea["measures"]} == {"poverty_rate", "no_vehicle_rate", "share_65_plus", "median_income"}
    income = next(m for m in ea["measures"] if m["measure"] == "median_income")
    assert income["ratio"] == 0.24
    assert [r["group"] for r in ea["racial_composition"]] == ["Black", "White"]


def test_adapter_labels_every_driver():
    resp = AgentApiResponse.model_validate(json.loads((SAMPLES / "site_selection_atlanta.json").read_text(encoding="utf-8")))
    sites = api._to_api_dict(resp)["recommendation"]["sites"]
    labels = {d["feature"]: d["label"] for s in sites for d in s["drivers"]}
    assert all(label != feature for feature, label in labels.items()), labels
