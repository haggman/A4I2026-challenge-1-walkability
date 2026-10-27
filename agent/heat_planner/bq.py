"""Single BigQuery client + parameterized SQL runner with cost & latency guardrails."""
from __future__ import annotations

import logging
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from google.cloud import bigquery

from .config import Settings

log = logging.getLogger(__name__)
SQL_DIR = Path(__file__).parent / "sql"


@lru_cache(maxsize=1)
def client() -> bigquery.Client:
    s = Settings()
    return bigquery.Client(project=s.project, location=s.bq_location)


@lru_cache(maxsize=32)
def load_sql(name: str) -> str:
    s = Settings()
    raw = (SQL_DIR / name).read_text(encoding="utf-8")
    return raw.replace("PROJECT", s.project).replace("MODEL_ID", s.bqml_model_id)


def _param(
    name: str, value: Any
) -> bigquery.ScalarQueryParameter | bigquery.ArrayQueryParameter:
    if isinstance(value, (list, tuple)):
        return bigquery.ArrayQueryParameter(name, "STRING", [str(v) for v in value])
    if isinstance(value, bool):
        return bigquery.ScalarQueryParameter(name, "BOOL", value)
    if isinstance(value, int):
        return bigquery.ScalarQueryParameter(name, "INT64", value)
    if isinstance(value, float):
        return bigquery.ScalarQueryParameter(name, "FLOAT64", value)
    return bigquery.ScalarQueryParameter(name, "STRING", str(value))


def run(
    sql: str,
    *,
    tool: str,
    timeout_s: float = 30.0,
    **params: Any,
) -> list[dict[str, Any]]:
    s = Settings()
    job_config = bigquery.QueryJobConfig(
        query_parameters=[_param(k, v) for k, v in params.items()],
        maximum_bytes_billed=s.max_bytes_billed,
        labels={"app": "heat-planner", "tool": tool.lower().replace("_", "-")[:60]},
    )
    t0 = time.monotonic()
    job = client().query(sql, job_config=job_config)
    rows = [dict(r) for r in job.result(timeout=timeout_s)]
    log.info(
        "bq tool=%s rows=%d bytes=%s ms=%d",
        tool,
        len(rows),
        job.total_bytes_processed,
        int((time.monotonic() - t0) * 1000),
    )
    return rows
