"""Write the UI-owned JSON schemas to docs/contracts/ (run from the repo root).

    python -m ui_service.export_schemas
"""

import json
from pathlib import Path

from .contracts import FinalResponse, VizSpec

OUT = Path("docs/contracts")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, model in (("viz_spec", VizSpec), ("final_response", FinalResponse)):
        path = OUT / f"{name}.schema.json"
        path.write_text(json.dumps(model.model_json_schema(by_alias=True), indent=2) + "\n", encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
