"""Unit tests for Pydantic v2 contracts, JSON schemas, sample payloads, and MCP Toolbox YAML."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from agent.heat_planner.callbacks import ALLOWED_MCP_TOOLS
from agent.heat_planner.schemas import (
    AgentApiResponse,
    DataRequest,
    Intent,
    Provenance,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "docs" / "contracts"
SAMPLES_DIR = CONTRACTS_DIR / "samples"
TOOLBOX_YAML = REPO_ROOT / "toolbox" / "tools.yaml"
SQL_DIR = REPO_ROOT / "agent" / "heat_planner" / "sql"


EXPECTED_SCHEMAS = [
    "intent.schema.json",
    "data_request.schema.json",
    "provenance.schema.json",
    "data_result.schema.json",
    "placement_recommendation.schema.json",
    "agent_api_response.schema.json",
]

EXPECTED_SAMPLES = [
    "site_selection_atlanta.json",
    "compare_site_4_atlanta.json",
    "explain_location_atlanta.json",
    "refusal_out_of_scope.json",
]


@pytest.mark.parametrize("filename", EXPECTED_SCHEMAS)
def test_exported_json_schemas_exist_and_forbid_extra_fields(filename: str) -> None:
    path = CONTRACTS_DIR / filename
    assert path.exists(), f"Missing exported schema: {path}"
    schema = json.loads(path.read_text(encoding="utf-8"))
    assert schema.get("additionalProperties") is False
    assert "properties" in schema
    assert "schema_version" in schema["properties"]


@pytest.mark.parametrize("filename", EXPECTED_SAMPLES)
def test_sample_payloads_validate_against_agent_api_response(filename: str) -> None:
    path = SAMPLES_DIR / filename
    assert path.exists(), f"Missing sample payload: {path}"
    raw = path.read_text(encoding="utf-8")
    resp = AgentApiResponse.model_validate_json(raw)
    assert resp.schema_version == "1.0.0"
    assert resp.intent.schema_version == "1.0.0"
    assert resp.verification.passed is True


def test_pydantic_models_forbid_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Intent(
            intent_type="site_selection",
            unexpected_field="should_fail",  # type: ignore[call-arg]
        )

    with pytest.raises(ValidationError):
        DataRequest(
            intent_type="explain_location",
            mcp_tool_name="explain_point",
            extra_param=123,  # type: ignore[call-arg]
        )

    with pytest.raises(ValidationError):
        Provenance(
            provenance_id="P1",
            tool_name="explain_heat_offset",
            mcp_tool_name="explain_point",
            sql_object="a4i_ml.offset_model_v1",
            row_count=1,
            extra_field="nope",  # type: ignore[call-arg]
        )


def test_toolbox_yaml_queries_only_semantic_and_ml_layers() -> None:
    assert TOOLBOX_YAML.exists(), f"Missing {TOOLBOX_YAML}"
    raw_text = TOOLBOX_YAML.read_text(encoding="utf-8")
    assert "a4i_climate" not in raw_text, "toolbox/tools.yaml must never query raw a4i_climate tables"
    assert "a4i_core" not in raw_text, "toolbox/tools.yaml must never query internal a4i_core tables"
    assert "a4i_semantic" in raw_text
    assert "a4i_ml" in raw_text

    parsed = yaml.safe_load(raw_text)
    assert "heat-bq" in parsed["sources"]
    assert parsed["sources"]["heat-bq"]["kind"] == "bigquery"
    assert parsed["sources"]["heat-bq"]["location"] == "US"

    tools = parsed["tools"]
    assert set(tools.keys()) == ALLOWED_MCP_TOOLS
    toolset = set(parsed["toolsets"]["heat-planner"])
    assert toolset == ALLOWED_MCP_TOOLS


def test_local_sql_files_match_allowed_data_tools_and_avoid_raw_datasets() -> None:
    sql_files = {p.stem for p in SQL_DIR.glob("*.sql")}
    assert sql_files == ALLOWED_MCP_TOOLS
    for path in SQL_DIR.glob("*.sql"):
        content = path.read_text(encoding="utf-8")
        assert "a4i_climate" not in content, f"{path.name} references raw a4i_climate"
        assert "a4i_core" not in content, f"{path.name} references internal a4i_core"


def test_to_api_dict_equity_audit_measures_and_racial_composition() -> None:
    from agent.heat_planner.api import _to_api_dict

    sample_path = SAMPLES_DIR / "site_selection_atlanta.json"
    assert sample_path.exists(), f"Missing {sample_path}"
    raw = sample_path.read_text(encoding="utf-8")
    resp = AgentApiResponse.model_validate_json(raw)

    api_dict = _to_api_dict(resp)
    rec = api_dict.get("recommendation")
    assert rec is not None, "recommendation should not be None"
    ea = rec.get("equity_audit")
    assert ea is not None, "equity_audit should not be None"

    measures = ea.get("measures", [])
    assert len(measures) == 4, f"Expected 4 measures, got {len(measures)}: {measures}"
    measure_names = {m["measure"] for m in measures}
    assert measure_names == {"poverty_rate", "no_vehicle_rate", "share_65_plus", "median_income"}

    for m in measures:
        assert "measure" in m
        assert "sites_value" in m
        assert "city_value" in m
        assert "ratio" in m

    racial = ea.get("racial_composition", [])
    assert len(racial) == 2, f"Expected 2 racial composition rows, got {len(racial)}: {racial}"
    racial_groups = {r["group"] for r in racial}
    assert racial_groups == {"Black", "White"}

    for r in racial:
        assert "group" in r
        assert "sites_share" in r
        assert "city_share" in r

