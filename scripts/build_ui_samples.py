"""Regenerate ui_service/samples/ from docs/contracts/samples/ (run from the repo root).

Each live heat-planner-api sample goes through the API's own _to_api_dict adapter, so heat-ui's
mock mode serves exactly what POST /api/v1/plan would return for those questions.

    python scripts/build_ui_samples.py
"""

import json
from pathlib import Path

from agent.heat_planner.api import _to_api_dict
from agent.heat_planner.schemas import AgentApiResponse

SRC = Path("docs/contracts/samples")
OUT = Path("ui_service/samples")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for path in sorted(SRC.glob("*.json")):
        resp = AgentApiResponse.model_validate_json(path.read_text(encoding="utf-8"))
        data = _to_api_dict(resp)
        data["trace_id"] = f"tr_sample_{path.stem}"
        if data.get("recommendation"):
            data["recommendation"]["generated_at"] = "sample"
        target = OUT / path.name
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(target)


if __name__ == "__main__":
    main()
