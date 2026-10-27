"""ADK root_agent definition for the Atlanta Urban Heat Planning Assistant."""
from __future__ import annotations

import logging
import os

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from .callbacks import after_tool_callback, before_tool_callback
from .config import Settings
from .prompts import PROMPT_VERSION, system_instruction
from .tools import (
    assemble_placement_recommendation,
    compare_sites,
    explain_heat_offset,
    get_area_demographics,
    get_heat_frequency,
    rank_candidate_sites,
    resolve_location,
    run_equity_audit,
)

log = logging.getLogger(__name__)
_settings = Settings()

# Ensure Gemini 3 preview models resolve via Vertex AI `global` endpoint
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", _settings.project)
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", _settings.google_cloud_location)


def _mcp_toolsets() -> list:
    """Attach MCP Toolbox for Databases when TOOLBOX_URL is configured."""
    if not _settings.toolbox_url:
        log.info("TOOLBOX_URL not set; running with custom Python function tools only.")
        return []
    try:
        from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams

        base = _settings.toolbox_url.rstrip("/")
        url = f"{base}/mcp/{_settings.toolbox_toolset}" if "/mcp" not in base else base
        return [
            McpToolset(
                connection_params=StreamableHTTPConnectionParams(
                    url=url,
                    timeout=_settings.toolbox_timeout_s,
                ),
            )
        ]
    except Exception as exc:
        log.warning("Failed to attach McpToolset (%s); continuing with function tools.", exc)
        return []


def _seed_state(callback_context: CallbackContext) -> None:
    st = callback_context.state
    st.setdefault("city", _settings.city)
    st.setdefault("track", _settings.track)
    st.setdefault("prompt_version", PROMPT_VERSION)
    st.setdefault("model_version", _settings.bqml_model_id)
    st.setdefault("turn_provenance", [])


root_agent = LlmAgent(
    name="urban_heat_planner",
    model=_settings.agent_model,
    description=(
        f"Urban heat planning assistant for {_settings.city}, GA ({_settings.track} track): "
        "predicts street-level heat offsets with BigQuery ML (ML.EXPLAIN_PREDICT) via MCP Toolbox, "
        "quantifies expected >=95°F-equivalent hot days from GHCN station history, "
        "evaluates walkable census-tract vulnerability, audits equity post-hoc, "
        "and drafts council-ready Placement Recommendations."
    ),
    instruction=system_instruction(),
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
        top_p=0.95,
        max_output_tokens=4096,
    ),
    before_agent_callback=_seed_state,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
    tools=[
        resolve_location,
        explain_heat_offset,
        rank_candidate_sites,
        compare_sites,
        get_heat_frequency,
        get_area_demographics,
        run_equity_audit,
        assemble_placement_recommendation,
        *_mcp_toolsets(),
    ],
)
