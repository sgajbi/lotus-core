from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ingestion_service.app.services.reference_data_ingestion_service import (
    ReferenceDataIngestionService,
    get_reference_data_ingestion_service,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "records", "conflict_columns", "update_columns"),
    [
        (
            "upsert_benchmark_definitions",
            [{"benchmark_id": "BMK_001", "effective_from": "2026-01-01"}],
            ["benchmark_id", "effective_from"],
            [
                "benchmark_name",
                "benchmark_type",
                "benchmark_currency",
                "return_convention",
                "benchmark_status",
                "benchmark_family",
                "benchmark_provider",
                "rebalance_frequency",
                "classification_set_id",
                "classification_labels",
                "effective_to",
                "source_timestamp",
                "source_vendor",
                "source_record_id",
                "quality_status",
            ],
        ),
        (
            "upsert_benchmark_compositions",
            [
                {
                    "benchmark_id": "BMK_001",
                    "index_id": "IDX_001",
                    "composition_effective_from": "2026-01-01",
                }
            ],
            ["benchmark_id", "index_id", "composition_effective_from"],
            [
                "composition_effective_to",
                "composition_weight",
                "rebalance_event_id",
                "source_timestamp",
                "source_vendor",
                "source_record_id",
                "quality_status",
            ],
        ),
        (
            "upsert_indices",
            [{"index_id": "IDX_001", "effective_from": "2026-01-01"}],
            ["index_id", "effective_from"],
            [
                "index_name",
                "index_currency",
                "index_type",
                "index_status",
                "index_provider",
                "index_market",
                "classification_set_id",
                "classification_labels",
                "effective_to",
                "source_timestamp",
                "source_vendor",
                "source_record_id",
                "quality_status",
            ],
        ),
        (
            "upsert_index_price_series",
            [{"series_id": "SER_001", "index_id": "IDX_001", "series_date": "2026-01-01"}],
            ["series_id", "index_id", "series_date"],
            [
                "index_price",
                "series_currency",
                "value_convention",
                "source_timestamp",
                "source_vendor",
                "source_record_id",
                "quality_status",
            ],
        ),
        (
            "upsert_index_return_series",
            [{"series_id": "SER_001", "index_id": "IDX_001", "series_date": "2026-01-01"}],
            ["series_id", "index_id", "series_date"],
            [
                "index_return",
                "return_period",
                "return_convention",
                "series_currency",
                "source_timestamp",
                "source_vendor",
                "source_record_id",
                "quality_status",
            ],
        ),
        (
            "upsert_benchmark_return_series",
            [{"series_id": "SER_001", "benchmark_id": "BMK_001", "series_date": "2026-01-01"}],
            ["series_id", "benchmark_id", "series_date"],
            [
                "benchmark_return",
                "return_period",
                "return_convention",
                "series_currency",
                "source_timestamp",
                "source_vendor",
                "source_record_id",
                "quality_status",
            ],
        ),
        (
            "upsert_risk_free_series",
            [
                {
                    "series_id": "SER_001",
                    "risk_free_curve_id": "RFC_001",
                    "series_date": "2026-01-01",
                }
            ],
            ["series_id", "risk_free_curve_id", "series_date"],
            [
                "value",
                "value_convention",
                "day_count_convention",
                "compounding_convention",
                "series_currency",
                "source_timestamp",
                "source_vendor",
                "source_record_id",
                "quality_status",
            ],
        ),
        (
            "upsert_classification_taxonomy",
            [
                {
                    "classification_set_id": "TAX_001",
                    "taxonomy_scope": "portfolio",
                    "dimension_name": "asset_class",
                    "dimension_value": "EQUITY",
                    "effective_from": "2026-01-01",
                }
            ],
            [
                "classification_set_id",
                "taxonomy_scope",
                "dimension_name",
                "dimension_value",
                "effective_from",
            ],
            [
                "dimension_description",
                "effective_to",
                "source_timestamp",
                "source_vendor",
                "source_record_id",
                "quality_status",
            ],
        ),
    ],
)
async def test_reference_data_upsert_methods_delegate_to_upsert_many(
    method_name: str,
    records: list[dict[str, str]],
    conflict_columns: list[str],
    update_columns: list[str],
) -> None:
    db = AsyncMock(spec=AsyncSession)
    service = ReferenceDataIngestionService(db)
    service._upsert_many = AsyncMock()  # type: ignore[method-assign]

    await getattr(service, method_name)(records)

    service._upsert_many.assert_awaited_once()
    assert service._upsert_many.await_args.kwargs["records"] == records
    assert service._upsert_many.await_args.kwargs["conflict_columns"] == conflict_columns
    assert service._upsert_many.await_args.kwargs["update_columns"] == update_columns


@pytest.mark.asyncio
async def test_upsert_many_returns_without_db_calls_for_empty_records() -> None:
    db = AsyncMock(spec=AsyncSession)
    service = ReferenceDataIngestionService(db)

    await service._upsert_many(
        model=object,
        records=[],
        conflict_columns=["id"],
        update_columns=["name"],
    )

    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_get_reference_data_ingestion_service_wraps_db_session() -> None:
    db = AsyncMock(spec=AsyncSession)

    service = get_reference_data_ingestion_service(db)  # type: ignore[arg-type]

    assert isinstance(service, ReferenceDataIngestionService)
    assert service._db is db


@pytest.mark.asyncio
async def test_upsert_portfolio_benchmark_assignments_defaults_assignment_recorded_at() -> None:
    db = AsyncMock(spec=AsyncSession)
    service = ReferenceDataIngestionService(db)

    await service.upsert_portfolio_benchmark_assignments(
        [
            {
                "portfolio_id": "PORT_001",
                "benchmark_id": "BMK_001",
                "effective_from": "2026-01-01",
                "assignment_source": "benchmark_policy_engine",
                "assignment_status": "active",
                "source_system": "lotus-manage",
                "assignment_recorded_at": None,
            }
        ]
    )

    db.execute.assert_awaited_once()
    compiled_params = db.execute.await_args.args[0].compile().params
    assert isinstance(compiled_params["assignment_recorded_at_m0"], datetime)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_cash_account_masters_uses_cash_account_id_conflict_key() -> None:
    db = AsyncMock(spec=AsyncSession)
    service = ReferenceDataIngestionService(db)

    await service.upsert_cash_account_masters(
        [
            {
                "cash_account_id": "CASH-ACC-USD-001",
                "portfolio_id": "PORT_001",
                "security_id": "CASH_USD",
                "display_name": "USD Operating Cash",
                "account_currency": "USD",
                "lifecycle_status": "ACTIVE",
            }
        ]
    )

    compiled = str(db.execute.await_args.args[0].compile())
    assert "cash_account_masters" in compiled
    assert "ON CONFLICT (cash_account_id)" in compiled
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_lookthrough_components_uses_effective_key_conflict() -> None:
    db = AsyncMock(spec=AsyncSession)
    service = ReferenceDataIngestionService(db)

    await service.upsert_instrument_lookthrough_components(
        [
            {
                "parent_security_id": "FUND_001",
                "component_security_id": "ETF_001",
                "effective_from": "2026-01-01",
                "component_weight": "0.6000000000",
            }
        ]
    )

    compiled = str(db.execute.await_args.args[0].compile())
    assert "instrument_lookthrough_components" in compiled
    assert "ON CONFLICT (parent_security_id, component_security_id, effective_from)" in compiled
    db.commit.assert_awaited_once()
