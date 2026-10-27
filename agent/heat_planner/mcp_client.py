"""MCP Toolbox client with OIDC auth, 15s timeout, 1 retry on 502/503/504, and Provenance tracking."""
from __future__ import annotations

import json
import logging
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from . import bq
from .config import Settings
from .schemas import Provenance

log = logging.getLogger(__name__)

# Map each MCP tool name to the semantic/ML BigQuery object it queries
MCP_TOOL_SQL_OBJECTS: dict[str, str] = {
    "explain_point": "a4i_ml.offset_model_v1 + a4i_ml.point_features",
    "rank_sites_pool": "a4i_ml.grid_predictions + a4i_semantic.tract_features",
    "vulnerable_population": "a4i_semantic.tract_features",
    "site_hot_days": "a4i_semantic.station_daily_city",
    "city_heat_days_by_year": "a4i_semantic.station_daily_city",
    "tract_profile": "a4i_semantic.tract_features",
    "equity_audit": "a4i_semantic.tract_features + a4i_semantic.tract_audit_race",
    "hottest_measured_cells": "a4i_semantic.heat_cells",
    "hottest_predicted_cells": "a4i_ml.grid_predictions + a4i_semantic.tract_features",
    "city_baseline": "a4i_semantic.tract_features + a4i_semantic.station_daily_city + a4i_ml.campaign_footprint",
    "tract_layer": "a4i_semantic.dim_tract + a4i_ml.grid_predictions + TIGER/Line tract polygons",
}


def _fetch_id_token(audience: str) -> str | None:
    """Fetch a Google OIDC identity token for invoking private Cloud Run services."""
    if not audience.startswith("https://"):
        return None
    try:
        import google.auth.transport.requests
        from google.oauth2 import id_token

        req = google.auth.transport.requests.Request()
        tok = id_token.fetch_id_token(req, audience)
        if tok:
            return tok
    except Exception:
        pass
    try:
        out = subprocess.check_output(
            ["gcloud", "auth", "print-identity-token"],
            text=True,
            timeout=5.0,
            stderr=subprocess.DEVNULL,
        ).strip()
        if out:
            return out
    except Exception:
        pass
    return None


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Decode JSON-serialized array columns (`drivers_json`, `tract_geo_ids_json`) in-place."""
    out = dict(row)
    if "drivers_json" in out and "drivers" not in out:
        raw_d = out.get("drivers_json")
        if isinstance(raw_d, str):
            try:
                out["drivers"] = json.loads(raw_d)
            except Exception:
                out["drivers"] = []
        elif isinstance(raw_d, list):
            out["drivers"] = raw_d
        else:
            out["drivers"] = []
    if "tract_geo_ids_json" in out and "tract_geo_ids" not in out:
        raw_g = out.get("tract_geo_ids_json")
        if isinstance(raw_g, str):
            try:
                out["tract_geo_ids"] = json.loads(raw_g)
            except Exception:
                out["tract_geo_ids"] = []
        elif isinstance(raw_g, list):
            out["tract_geo_ids"] = raw_g
        else:
            out["tract_geo_ids"] = []
    return out


def _parse_toolbox_response(payload: Any) -> list[dict[str, Any]]:
    """Parse MCP Toolbox `/api/tool/<name>/invoke` response into a list of row dicts."""
    if isinstance(payload, list):
        return [_normalize_row(r) for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        res = payload.get("result")
        if isinstance(res, str):
            try:
                parsed = json.loads(res)
                if isinstance(parsed, list):
                    return [_normalize_row(r) for r in parsed if isinstance(r, dict)]
                if isinstance(parsed, dict):
                    return [_normalize_row(parsed)]
            except Exception:
                return []
        if isinstance(res, list):
            rows: list[dict[str, Any]] = []
            for item in res:
                if isinstance(item, dict):
                    rows.append(_normalize_row(item))
                elif isinstance(item, str):
                    try:
                        sub = json.loads(item)
                        if isinstance(sub, list):
                            rows.extend(_normalize_row(x) for x in sub if isinstance(x, dict))
                        elif isinstance(sub, dict):
                            rows.append(_normalize_row(sub))
                    except Exception:
                        continue
            return rows
    return []


def invoke_mcp_tool(
    mcp_tool_name: str,
    *,
    tool_name: str,
    provenance_list: list[Provenance] | None = None,
    **params: Any,
) -> tuple[list[dict[str, Any]], Provenance]:
    """Invoke a named MCP tool on `heat-toolbox` (or fallback to mirrored SQL in `sql/`)
    and record a typed `Provenance` entry.

    Implements a 15s per-call timeout and 1 automatic retry with 0.5s backoff on 502/503/504.
    """
    s = Settings()
    base_url = (s.toolbox_url or "").rstrip("/")
    sql_object = MCP_TOOL_SQL_OBJECTS.get(mcp_tool_name, f"a4i_semantic.{mcp_tool_name}")
    rows: list[dict[str, Any]] | None = None

    if base_url:
        invoke_url = f"{base_url}/api/tool/{mcp_tool_name}/invoke"
        headers = {"Content-Type": "application/json"}
        tok = _fetch_id_token(base_url)
        if tok:
            headers["Authorization"] = f"Bearer {tok}"

        for attempt in range(2):
            try:
                with httpx.Client(timeout=s.toolbox_timeout_s) as http:
                    resp = http.post(invoke_url, json=params, headers=headers)
                    if resp.status_code in (502, 503, 504) and attempt == 0:
                        log.warning(
                            "MCP Toolbox %s returned %d on attempt 1; retrying in %.1fs",
                            mcp_tool_name,
                            resp.status_code,
                            s.toolbox_retry_backoff_s,
                        )
                        time.sleep(s.toolbox_retry_backoff_s)
                        continue
                    resp.raise_for_status()
                    rows = _parse_toolbox_response(resp.json())
                    break
            except Exception as exc:
                if attempt == 0:
                    time.sleep(s.toolbox_retry_backoff_s)
                    continue
                log.warning(
                    "MCP Toolbox HTTP call failed for %s (%s); falling back to parameterized SQL.",
                    mcp_tool_name,
                    exc,
                )

    if rows is None:
        raw_rows = bq.run(
            bq.load_sql(f"{mcp_tool_name}.sql"),
            tool=tool_name,
            **params,
        )
        rows = [_normalize_row(r) for r in raw_rows]

    next_idx = (len(provenance_list) + 1) if provenance_list is not None else 1
    prov = Provenance(
        provenance_id=f"P{next_idx}",
        source_type="mcp_toolbox",
        tool_name=tool_name,
        mcp_tool_name=mcp_tool_name,
        sql_object=sql_object,
        parameters={k: v for k, v in params.items()},
        row_count=len(rows),
        model_version=s.bqml_model_id,
        queried_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    if provenance_list is not None:
        provenance_list.append(prov)
    return rows, prov
