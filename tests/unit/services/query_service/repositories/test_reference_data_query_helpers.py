"""Tests for deterministic reference-data query construction."""

from datetime import date

from sqlalchemy import Column, Date, DateTime, Integer, MetaData, String, Table
from sqlalchemy.dialects import postgresql

from src.services.query_service.app.repositories.reference_data_query_helpers import (
    canonical_series_ranked_subquery,
    effective_filter,
    normalize_reference_status,
    ranked_latest_effective_ids,
)

REFERENCE_SERIES = Table(
    "reference_series",
    MetaData(),
    Column("id", Integer),
    Column("portfolio_id", String),
    Column("effective_from", Date),
    Column("effective_to", Date),
    Column("quality_status", String),
    Column("source_timestamp", DateTime(timezone=True)),
    Column("series_id", String),
    Column("source_vendor", String),
    Column("source_record_id", String),
)


def _postgres_sql(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_effective_filter_keeps_open_or_current_records() -> None:
    predicate = effective_filter(
        REFERENCE_SERIES.c.effective_from,
        REFERENCE_SERIES.c.effective_to,
        date(2026, 4, 10),
    )

    sql = _postgres_sql(predicate)

    assert "effective_from <= '2026-04-10'" in sql
    assert "effective_to IS NULL" in sql
    assert "effective_to >= '2026-04-10'" in sql


def test_normalize_reference_status_is_case_and_whitespace_insensitive() -> None:
    assert normalize_reference_status("  ACCEPTED  ") == "accepted"


def test_canonical_series_ranking_prefers_accepted_and_latest_source_evidence() -> None:
    ranked = canonical_series_ranked_subquery(
        REFERENCE_SERIES.c,
        REFERENCE_SERIES.c.portfolio_id,
        predicates=[REFERENCE_SERIES.c.effective_from <= date(2026, 4, 10)],
    )

    sql = _postgres_sql(ranked)

    assert "row_number() OVER" in sql
    assert "PARTITION BY reference_series.portfolio_id" in sql
    assert "upper(trim(reference_series.quality_status)) = 'ACCEPTED'" in sql
    assert "reference_series.source_timestamp DESC NULLS LAST" in sql
    assert "reference_series.series_id DESC" in sql
    assert "reference_series.source_vendor DESC NULLS LAST" in sql
    assert "reference_series.source_record_id DESC NULLS LAST" in sql
    assert "reference_series.id DESC" in sql
    assert "effective_from <= '2026-04-10'" in sql


def test_latest_effective_ranking_honors_domain_partition_and_order() -> None:
    ranked = ranked_latest_effective_ids(
        REFERENCE_SERIES.c,
        REFERENCE_SERIES.c.portfolio_id,
        predicates=[REFERENCE_SERIES.c.effective_from <= date(2026, 4, 10)],
        order_by=(
            REFERENCE_SERIES.c.effective_from.desc(),
            REFERENCE_SERIES.c.id.desc(),
        ),
    )

    sql = _postgres_sql(ranked)

    assert "PARTITION BY reference_series.portfolio_id" in sql
    assert "ORDER BY reference_series.effective_from DESC, reference_series.id DESC" in sql
    assert "effective_from <= '2026-04-10'" in sql
