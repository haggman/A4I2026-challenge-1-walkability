"""Typed runtime settings, read once from the environment.

Nothing else in the agent reads os.environ, so every knob that can differ between
local dev, Cloud Run and Agent Runtime is visible in one place.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    project: str
    location: str              # Gemini platform region, e.g. us-central1
    bq_location: str           # BigQuery location of the datasets ("US")
    data_dataset: str          # a4i_climate (raw, loaded by notebook/load.sh)
    ml_dataset: str            # a4i_ml (features, models, grid predictions)
    model_id: str              # promoted BQML model, e.g. offset_model_v1
    agent_model: str           # fast Gemini model for the tool loop
    writer_model: str          # stronger Gemini model for drafting proposals
    city: str
    track: str                 # today | budget | decade
    toolbox_url: str           # "" disables the MCP toolset
    maps_api_key: str          # "" disables geocoding (coordinates still work)
    max_bytes_billed: int

    @property
    def model_ref(self) -> str:
        return f"`{self.project}.{self.ml_dataset}.{self.model_id}`"


@lru_cache(maxsize=1)
def settings() -> Settings:
    env = os.environ.get
    return Settings(
        project=env("GOOGLE_CLOUD_PROJECT", ""),
        location=env("GOOGLE_CLOUD_LOCATION", "us-central1"),
        bq_location=env("BQ_LOCATION", "US"),
        data_dataset=env("DATA_DATASET", "a4i_climate"),
        ml_dataset=env("ML_DATASET", "a4i_ml"),
        model_id=env("BQML_MODEL_ID", "offset_model_v1"),
        agent_model=env("AGENT_MODEL", ""),     # set explicitly; verify current GA id
        writer_model=env("WRITER_MODEL", ""),
        city=env("CITY", "Dallas"),
        track=env("TRACK", "budget"),
        toolbox_url=env("TOOLBOX_URL", ""),
        maps_api_key=env("MAPS_API_KEY", ""),
        max_bytes_billed=int(env("MAX_BYTES_BILLED", str(1_000_000_000))),
    )
