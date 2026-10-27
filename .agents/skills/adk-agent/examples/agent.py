"""root_agent for the heat planning assistant.

Check import paths against the installed google-adk version (`pip show google-adk`);
the MCP toolset classes have moved between releases.
"""
from __future__ import annotations

import logging

import google.auth.transport.requests
import google.oauth2.id_token
from google.adk.agents import Agent

from .config import settings
from .prompts import system_instruction
from .tools.audit import run_equity_audit
from .tools.demographics import get_area_demographics
from .tools.heat_model import explain_heat_offset, rank_candidate_sites
from .tools.history import get_heat_frequency
from .tools.location import resolve_location
from .tools.recommendation import assemble_placement_recommendation

log = logging.getLogger(__name__)
s = settings()

tools: list = [
    resolve_location,
    explain_heat_offset,
    rank_candidate_sites,
    get_heat_frequency,
    get_area_demographics,
    run_equity_audit,
    assemble_placement_recommendation,
]


def _toolbox_toolset():
    """MCP Toolbox on Cloud Run (private): authenticate with a Google ID token for its URL."""
    from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams

    def _headers(_ctx=None) -> dict[str, str]:
        token = google.oauth2.id_token.fetch_id_token(
            google.auth.transport.requests.Request(), s.toolbox_url)
        return {"Authorization": f"Bearer {token}"}

    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(url=f"{s.toolbox_url}/mcp"),
        header_provider=_headers,          # refreshes per session; ID tokens expire in ~1 h
        tool_filter=None,                  # or a list of read-only tool names from tools.yaml
    )


if s.toolbox_url:
    try:
        tools.append(_toolbox_toolset())
    except Exception:  # agent must still start if the Toolbox is down
        log.exception("MCP Toolbox unavailable; continuing with built-in tools only")

root_agent = Agent(
    name="heat_planner",
    model=s.agent_model,
    description=f"Heat planning assistant for {s.city}: where heat help should go, and why.",
    instruction=system_instruction(),
    tools=tools,
)
