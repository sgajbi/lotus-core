"""SQL adapter tests for benchmark definition evidence."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.query_control_plane_service.app.infrastructure import benchmark_definition_sources


def _session_returning(*rows: object) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.first.return_value = rows[0] if rows else None
    result.scalars.return_value.all.return_value = list(rows)
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    return session


def _timestamps() -> dict[str, datetime]:
    return {
        "source_timestamp": datetime(2026, 4, 10, 9, tzinfo=UTC),
        "created_at": datetime(2026, 4, 10, 8, tzinfo=UTC),
        "updated_at": datetime(2026, 4, 10, 10, tzinfo=UTC),
    }


@pytest.mark.asyncio
async def test_definition_query_uses_full_deterministic_tie_breaking() -> None:
    row = SimpleNamespace(
        benchmark_id="BMK_1",
        benchmark_name="Benchmark 1",
        benchmark_type="composite",
        benchmark_currency="SGD",
        return_convention="total_return_index",
        benchmark_status="active",
        benchmark_family="multi_asset",
        benchmark_provider="provider",
        rebalance_frequency="quarterly",
        classification_set_id="taxonomy_1",
        classification_labels={"asset_class": "multi_asset"},
        effective_from=date(2026, 1, 1),
        effective_to=None,
        source_vendor="provider",
        source_record_id="benchmark:1",
        quality_status="accepted",
        **_timestamps(),
    )
    session = _session_returning(row)

    evidence = await benchmark_definition_sources.SqlAlchemyBenchmarkDefinitionReader(
        session
    ).resolve_definition(benchmark_id="BMK_1", as_of_date=date(2026, 4, 10))

    assert evidence is not None
    assert evidence.classification_labels == {"asset_class": "multi_asset"}
    sql = str(session.execute.await_args.args[0])
    assert "benchmark_definitions.effective_from <=" in sql
    assert "benchmark_definitions.source_timestamp DESC NULLS LAST" in sql
    assert "benchmark_definitions.id DESC" in sql


@pytest.mark.asyncio
async def test_component_query_ranks_each_index_and_orders_output() -> None:
    row = SimpleNamespace(
        benchmark_id="BMK_1",
        index_id="IDX_1",
        composition_effective_from=date(2026, 1, 1),
        composition_effective_to=None,
        composition_weight="1.0000000000",
        rebalance_event_id="rebalance_1",
        source_vendor="provider",
        source_record_id="component:1",
        quality_status="accepted",
        **_timestamps(),
    )
    session = _session_returning(row)

    evidence = await benchmark_definition_sources.SqlAlchemyBenchmarkDefinitionReader(
        session
    ).list_components(benchmark_id="BMK_1", as_of_date=date(2026, 4, 10))

    assert evidence[0].composition_weight.as_tuple().exponent == -10
    sql = str(session.execute.await_args.args[0])
    assert "row_number() OVER" in sql
    assert "benchmark_composition_series.index_id" in sql
    assert "benchmark_composition_series.source_timestamp DESC NULLS LAST" in sql
    assert "ORDER BY benchmark_composition_series.index_id ASC" in sql


@pytest.mark.asyncio
async def test_overlapping_definition_query_is_window_bounded_and_stably_ordered() -> None:
    row = SimpleNamespace(
        benchmark_id="BMK_1",
        benchmark_name="Benchmark 1",
        benchmark_type="composite",
        benchmark_currency="USD",
        return_convention="total_return_index",
        benchmark_status="active",
        benchmark_family=None,
        benchmark_provider="provider",
        rebalance_frequency="quarterly",
        classification_set_id=None,
        classification_labels={},
        effective_from=date(2026, 1, 1),
        effective_to=None,
        source_vendor="provider",
        source_record_id="definition:1",
        quality_status="accepted",
        **_timestamps(),
    )
    session = _session_returning(row)

    records = await benchmark_definition_sources.SqlAlchemyBenchmarkDefinitionReader(
        session
    ).list_definitions_overlapping_window(
        benchmark_id="BMK_1",
        start_date=date(2026, 1, 15),
        end_date=date(2026, 3, 31),
    )

    assert records[0].benchmark_currency == "USD"
    sql = str(session.execute.await_args.args[0])
    assert "benchmark_definitions.effective_from <=" in sql
    assert "benchmark_definitions.effective_to IS NULL" in sql
    assert "benchmark_definitions.source_timestamp ASC NULLS LAST" in sql


@pytest.mark.asyncio
async def test_overlapping_component_query_preserves_all_rebalance_segments() -> None:
    row = SimpleNamespace(
        benchmark_id="BMK_1",
        index_id="IDX_1",
        composition_effective_from=date(2026, 1, 1),
        composition_effective_to=None,
        composition_weight="1.0000000000",
        rebalance_event_id="rebalance_1",
        source_vendor="provider",
        source_record_id="component:1",
        quality_status="accepted",
        **_timestamps(),
    )
    session = _session_returning(row)

    records = await benchmark_definition_sources.SqlAlchemyBenchmarkDefinitionReader(
        session
    ).list_components_overlapping_window(
        benchmark_id="BMK_1",
        start_date=date(2026, 1, 15),
        end_date=date(2026, 3, 31),
    )

    assert records[0].composition_weight == Decimal("1.0000000000")
    sql = str(session.execute.await_args.args[0])
    assert "benchmark_composition_series.composition_effective_from <=" in sql
    assert "benchmark_composition_series.composition_effective_to IS NULL" in sql
    assert "benchmark_composition_series.index_id ASC" in sql


@pytest.mark.asyncio
async def test_catalog_definition_query_normalizes_filters_and_ranks_current_rows() -> None:
    row = SimpleNamespace(
        benchmark_id="BMK_1",
        benchmark_name="Benchmark 1",
        benchmark_type="composite",
        benchmark_currency="USD",
        return_convention="total_return_index",
        benchmark_status="active",
        benchmark_family=None,
        benchmark_provider="provider",
        rebalance_frequency="quarterly",
        classification_set_id=None,
        classification_labels={},
        effective_from=date(2026, 1, 1),
        effective_to=None,
        source_vendor="provider",
        source_record_id="definition:1",
        quality_status="accepted",
        **_timestamps(),
    )
    session = _session_returning(row)

    records = await benchmark_definition_sources.SqlAlchemyBenchmarkDefinitionReader(
        session
    ).list_definitions(
        as_of_date=date(2026, 4, 10),
        benchmark_type=" Composite ",
        benchmark_currency=" usd ",
        benchmark_status=" ACTIVE ",
    )

    assert records[0].benchmark_id == "BMK_1"
    sql = str(session.execute.await_args.args[0])
    assert "row_number() OVER" in sql
    assert "benchmark_definitions.benchmark_type" in sql
    assert "benchmark_definitions.benchmark_currency" in sql
    assert "benchmark_definitions.benchmark_status" in sql
    assert "ORDER BY benchmark_definitions.benchmark_id ASC" in sql


@pytest.mark.asyncio
async def test_catalog_component_query_groups_current_rows_by_benchmark() -> None:
    row = SimpleNamespace(
        benchmark_id="BMK_1",
        index_id="IDX_1",
        composition_effective_from=date(2026, 1, 1),
        composition_effective_to=None,
        composition_weight="1.0000000000",
        rebalance_event_id="rebalance_1",
        source_vendor="provider",
        source_record_id="component:1",
        quality_status="accepted",
        **_timestamps(),
    )
    session = _session_returning(row)

    grouped = await benchmark_definition_sources.SqlAlchemyBenchmarkDefinitionReader(
        session
    ).list_components_for_benchmarks(benchmark_ids=["BMK_1"], as_of_date=date(2026, 4, 10))

    assert grouped["BMK_1"][0].index_id == "IDX_1"
    sql = str(session.execute.await_args.args[0])
    assert "row_number() OVER" in sql
    assert "benchmark_composition_series.benchmark_id IN" in sql
    assert "benchmark_composition_series.index_id ASC" in sql
