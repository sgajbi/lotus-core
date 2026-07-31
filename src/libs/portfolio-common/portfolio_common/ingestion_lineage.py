from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

INGESTION_JOB_ID_HEADER = "ingestion_job_id"
ingestion_job_id_var: ContextVar[str | None] = ContextVar(
    "ingestion_job_id",
    default=None,
)


def normalize_ingestion_job_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


@contextmanager
def ingestion_job_scope(job_id: str | None) -> Iterator[None]:
    normalized = normalize_ingestion_job_id(job_id)
    token = ingestion_job_id_var.set(normalized)
    try:
        yield
    finally:
        ingestion_job_id_var.reset(token)
