from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from src.services.ingestion_service.app.services.ingestion_job_listing import (
    IngestionJobListFilters,
    build_ingestion_job_list_statement,
    ingestion_job_list_page,
)


def test_ingestion_job_list_page_returns_rows_and_next_cursor():
    rows = [
        SimpleNamespace(job_id="job_3"),
        SimpleNamespace(job_id="job_2"),
        SimpleNamespace(job_id="job_1"),
    ]

    page = ingestion_job_list_page(rows=rows, limit=2)

    assert [row.job_id for row in page.rows] == ["job_3", "job_2"]
    assert page.next_cursor == "job_2"


def test_ingestion_job_list_page_has_no_cursor_when_final_page():
    rows = [SimpleNamespace(job_id="job_1")]

    page = ingestion_job_list_page(rows=rows, limit=2)

    assert [row.job_id for row in page.rows] == ["job_1"]
    assert page.next_cursor is None


def test_build_ingestion_job_list_statement_applies_filters_and_cursor():
    statement = build_ingestion_job_list_statement(
        filters=IngestionJobListFilters(
            status="accepted",
            entity_type="transaction",
            submitted_from=datetime(2026, 6, 1, tzinfo=UTC),
            submitted_to=datetime(2026, 6, 5, tzinfo=UTC),
        ),
        cursor_row=SimpleNamespace(id=100),
        limit=25,
    )

    compiled_sql = str(statement)

    assert "ingestion_jobs.status = :status_1" in compiled_sql
    assert "ingestion_jobs.entity_type = :entity_type_1" in compiled_sql
    assert "ingestion_jobs.submitted_at >= :submitted_at_1" in compiled_sql
    assert "ingestion_jobs.submitted_at <= :submitted_at_2" in compiled_sql
    assert "ingestion_jobs.id < :id_1" in compiled_sql
    assert "ORDER BY ingestion_jobs.id DESC" in compiled_sql
