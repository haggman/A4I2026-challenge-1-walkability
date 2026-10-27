"""Export Pydantic v2 JSON Schemas to `docs/contracts/*.schema.json` and live sample payloads to `docs/contracts/samples/*.json`."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))

# Disable LLM writer during deterministic sample generation so samples are 100% reproducible
os.environ["USE_LLM_WRITER"] = "false"

from heat_planner.orchestrator import run_plan_turn  # noqa: E402
from heat_planner.schemas import (  # noqa: E402
    AgentApiResponse,
    DataRequest,
    DataResult,
    Intent,
    PlacementRecommendation,
    Provenance,
)


def main() -> None:
    contracts_dir = ROOT / "docs" / "contracts"
    samples_dir = contracts_dir / "samples"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    samples_dir.mkdir(parents=True, exist_ok=True)

    schema_map = {
        "intent.schema.json": Intent.model_json_schema(),
        "data_request.schema.json": DataRequest.model_json_schema(),
        "provenance.schema.json": Provenance.model_json_schema(),
        "data_result.schema.json": DataResult.model_json_schema(),
        "placement_recommendation.schema.json": PlacementRecommendation.model_json_schema(),
        "agent_api_response.schema.json": AgentApiResponse.model_json_schema(),
    }
    for filename, schema_obj in schema_map.items():
        out_path = contracts_dir / filename
        out_path.write_text(json.dumps(schema_obj, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {out_path.relative_to(ROOT)}")

    session_state: dict = {}

    # 1. site_selection_atlanta.json
    resp_site_sel = run_plan_turn(
        "Where should Atlanta open 3 walkable cooling centers this budget cycle, and why?",
        session_state=session_state,
    )
    (samples_dir / "site_selection_atlanta.json").write_text(
        json.dumps(resp_site_sel.model_dump(), indent=2) + "\n", encoding="utf-8"
    )
    print("Wrote docs/contracts/samples/site_selection_atlanta.json")

    # 2. compare_site_4_atlanta.json (reuses session_state from turn 1)
    resp_cmp = run_plan_turn(
        "Why not Site #4 instead of one of the top 3 cooling centers?",
        session_state=session_state,
    )
    (samples_dir / "compare_site_4_atlanta.json").write_text(
        json.dumps(resp_cmp.model_dump(), indent=2) + "\n", encoding="utf-8"
    )
    print("Wrote docs/contracts/samples/compare_site_4_atlanta.json")

    # 3. explain_location_atlanta.json
    resp_explain = run_plan_turn(
        "What is the predicted heat offset in Venetian Hills on a 98°F forecast day, and what drives it?",
        session_state=session_state,
    )
    (samples_dir / "explain_location_atlanta.json").write_text(
        json.dumps(resp_explain.model_dump(), indent=2) + "\n", encoding="utf-8"
    )
    print("Wrote docs/contracts/samples/explain_location_atlanta.json")

    # 4. refusal_out_of_scope.json
    resp_refusal = run_plan_turn(
        "Where should Phoenix, AZ place 3 cooling centers this summer?",
        session_state=session_state,
    )
    (samples_dir / "refusal_out_of_scope.json").write_text(
        json.dumps(resp_refusal.model_dump(), indent=2) + "\n", encoding="utf-8"
    )
    print("Wrote docs/contracts/samples/refusal_out_of_scope.json")


if __name__ == "__main__":
    main()
