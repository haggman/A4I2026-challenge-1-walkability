"""Single BigQuery entry point: parameterized, byte-capped, timed, logged."""
from __future__ import annotations

import logging
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from google.cloud import bigquery

from .config import settings

log = logging.getLogger(__name__)
SQL_DIR = Path(__file__).parent / "sql"


@lru_cache(maxsize=1)
def client() -> bigquery.Client:
    s = settings()
    return bigquery.Client(project=s.project, location=s.bq_location)


def load_sql(name: str) -> str:
    """Load sql/<name>.sql and fill structural placeholders (never user input)."""
    s = settings()
    text = (SQL_DIR / f"{name}.sql").read_text()
    return (text.replace("PROJECT", s.project)
                .replace("offset_model_v1", s.model_id))


def _param(name: str, value: Any) -> bigquery.ScalarQueryParameter:
    kind = {float: "FLOAT64", int: "INT64", bool: "BOOL", str: "STRING"}[type(value)]
    return bigquery.ScalarQueryParameter(name, kind, value)


def run(sql: str, tool: str, timeout_s: float = 30.0, **params: Any) -> list[dict]:
    s = settings()
    cfg = bigquery.QueryJobConfig(
        query_parameters=[_param(k, v) for k, v in params.items()],
        maximum_bytes_billed=s.max_bytes_billed,
        labels={"app": "heat-planner", "tool": tool.replace("_", "-")},
    )
    t0 = time.monotonic()
    job = client().query(sql, job_config=cfg)
    rows = [dict(r) for r in job.result(timeout=timeout_s)]
    log.info("bq_query", extra={
        "tool": tool, "rows": len(rows),
        "bytes": job.total_bytes_processed,
        "latency_ms": int((time.monotonic() - t0) * 1000),
    })
    return rows
