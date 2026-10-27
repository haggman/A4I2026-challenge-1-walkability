"""Runtime configuration for the Atlanta Urban Heat Planning Assistant (Gemini 3 + MCP Toolbox).

Every setting reads from environment variables with defaults matching
`qwiklabs-gcp-04-ec3596addc43` (Atlanta, GA · `budget` track · `gemini-3-flash-preview`).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

# Ensure google-genai uses Vertex AI in global location for Gemini 3 preview models
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-04-ec3596addc43")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")


def _env(name: str, default: str | None = None) -> str:
    val = os.getenv(name, default)
    if val is None or val == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


@dataclass(frozen=True)
class Settings:
    project: str = _env("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-04-ec3596addc43")
    google_cloud_location: str = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
    compute_region: str = os.getenv("COMPUTE_REGION", "us-central1")
    bq_location: str = os.getenv("BQ_LOCATION", "US")

    city: str = os.getenv("CITY", "Atlanta")
    track: str = os.getenv("TRACK", "budget")  # today | budget | decade
    scenario_sites: int = int(os.getenv("SCENARIO_SITES", "3"))

    bqml_model_id: str = os.getenv("BQML_MODEL_ID", "offset_model_v1")
    agent_model: str = os.getenv("AGENT_MODEL", "gemini-3-flash-preview")
    writer_model: str = os.getenv("WRITER_MODEL", "gemini-3-flash-preview")
    use_llm_writer: bool = os.getenv("USE_LLM_WRITER", "false").lower() in ("1", "true", "yes")

    toolbox_url: str | None = os.getenv("TOOLBOX_URL") or None
    toolbox_toolset: str = os.getenv("TOOLBOX_TOOLSET", "heat-planner")
    toolbox_timeout_s: float = float(os.getenv("TOOLBOX_TIMEOUT_S", "15.0"))
    toolbox_retry_backoff_s: float = float(os.getenv("TOOLBOX_RETRY_BACKOFF_S", "0.5"))

    # Atlanta metro bounding box for fast pre-BQ coordinate guardrails
    lat_min: float = 33.4
    lat_max: float = 34.1
    lon_min: float = -84.8
    lon_max: float = -84.0

    maps_api_key: str | None = os.getenv("MAPS_API_KEY") or None
    max_bytes_billed: int = int(os.getenv("MAX_BYTES_BILLED", str(2 * 1024**3)))

    @property
    def location(self) -> str:
        return self.google_cloud_location

    @property
    def bqml_model_fqn(self) -> str:
        return f"{self.project}.a4i_ml.{self.bqml_model_id}"
