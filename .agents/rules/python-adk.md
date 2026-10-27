---
trigger: glob
globs: "agent/**/*.py, frontend/**/*.py, tests/**/*.py"
description: Python and ADK conventions for the heat planning agent.
---

# Python / ADK conventions

- `root_agent` is defined in `agent/heat_planner/agent.py`; `agent/heat_planner/__init__.py`
  contains `from . import agent`. `adk web` and `adk deploy` are run from `agent/`.
- Every function tool has a complete docstring (summary, Args, Returns). ADK sends it to Gemini
  as the tool description, so it is part of the prompt. Write it for the model, not the reader.
- Tool parameters are primitives (`float`, `str`, `int`, `list[str]`). No `Optional[...]` with
  default `None` unless needed. Defaults must be JSON-serializable.
- Tools return `dict` built from a Pydantic model via `.model_dump()`. Always include
  `status: "ok" | "no_data" | "out_of_scope" | "error"`. On failure, return `error_message`
  in plain English that the model can relay. Never raise into the agent loop.
- One BigQuery client per process (module-level, lazily created). Pass parameters with
  `bigquery.ScalarQueryParameter`. Never f-string user input into SQL.
- Set `maximum_bytes_billed` on every query job (default 1 GB) and a timeout.
- Config comes from `agent/heat_planner/config.py`, which reads env vars once. Model IDs,
  project, dataset, model name and Toolbox URL are config, never literals in tool code.
- Log with `logging` (structured `extra=` fields: tool, lat, lon, latency_ms, bytes). Cloud
  Logging picks it up on Cloud Run and Agent Runtime.
- Tests: `pytest`, with BigQuery mocked at the client boundary for unit tests. Live
  tests are marked `@pytest.mark.live`.
