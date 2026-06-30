from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ingestion_service.app.services.reference_data_ingestion_service import (
    ReferenceDataIngestionService,
    ReferenceDataUpsertOperation,
    get_reference_data_ingestion_service,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "records", "conflict_columns", "update_columns"),
    [
        (
            "upsert_model_portfolio_definitions",
            [
                {
                    "model_portfolio_id": "MODEL_SG_BALANCED_DPM",
                    "model_portfolio_version": "2026.03",
                    "base_currency": "SGD",
                    "effective_from": "2026-03-25",
                }
            ],
            ["model_portfolio_id", "model_portfolio_version", "effective_from"],
            [
                "display_name",
                "base_currency",
                "risk_profile",
                "mandate_type",
                "rebalance_frequency",
                "approval_status",
                "approved_at",
                "effective_to",
                "source_system",
                "source_record_id",
                "observed_at",
                "quality_status",
            ],
        ),
        (
            "upsert_model_portfolio_targets",
            [
                {
                    "model_portfolio_id": "MODEL_SG_BALANCED_DPM",
                    "model_portfolio_version": "2026.03",
                    "instrument_id": "EQ_US_AAPL",
                    "effective_from": "2026-03-25",
                }
            ],
            ["model_portfolio_id", "model_portfolio_version", "instrument_id", "effective_from"],
            [
                "target_weight",
                "min_weight",
                "max_weight",
                "target_status",
                "effective_to",
                "source_system",
                "source_record_id",
                "observed_at",
                "quality_status",
            ],
        ),
        (
            "upsert_discretionary_mandate_bindings",
            [
                {
                    "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                    "mandate_id": "MANDATE_PB_SG_GLOBAL_BAL_001",
                    "effective_from": "2026-04-01",
                    "binding_version": "1",
                }
            ],
            ["portfolio_id", "mandate_id", "effective_from", "binding_version"],
            [
                "client_id",
                "mandate_type",
                "discretionary_authority_status",
                "booking_center_code",
                "jurisdiction_code",
                "model_portfolio_id",
                "policy_pack_id",
                "mandate_objective",
                "risk_profile",
                "investment_horizon",
                "review_cadence",
                "last_review_date",
                "next_review_due_date",
                "leverage_allowed",
                "tax_awareness_allowed",
                "settlement_awareness_required",
                "rebalance_frequency",
                "rebalance_bands",
                "effective_to",
                "source_system",
                "source_record_id",
                "observed_at",
                "quality_status",
            ],
        ),
        (
            "upsert_instrument_eligibility_profiles",
            [
                {
                    "security_id": "AAPL",
                    "effective_from": "2026-04-01",
                    "eligibility_version": "1",
                }
            ],
            ["security_id", "effective_from", "eligibility_version"],
            [
                "eligibility_status",
                "product_shelf_status",
                "buy_allowed",
                "sell_allowed",
                "restriction_reason_codes",
                "restriction_rationale",
                "settlement_days",
                "settlement_calendar_id",
                "liquidity_tier",
                "issuer_id",
                "issuer_name",
                "ultimate_parent_issuer_id",
                "ultimate_parent_issuer_name",
                "asset_class",
                "country_of_risk",
                "effective_to",
                "source_system",
                "source_record_id",
                "observed_at",
                "quality_status",
            ],
        ),
        (
            "upsert_client_restriction_profiles",
            [
                {
                    "client_id": "CIF_SG_000184",
                    "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                    "restriction_code": "NO_PRIVATE_CREDIT_BUY",
                    "effective_from": "2026-04-01",
                    "restriction_version": "1",
                }
            ],
            [
                "client_id",
                "portfolio_id",
                "restriction_code",
                "effective_from",
                "restriction_version",
            ],
            [
                "mandate_id",
                "restriction_scope",
                "restriction_status",
                "restriction_source",
                "applies_to_buy",
                "applies_to_sell",
                "instrument_ids",
                "asset_classes",
                "issuer_ids",
                "country_codes",
                "effective_to",
                "source_system",
                "source_record_id",
                "observed_at",
                "quality_status",
            ],
        ),
        (
            "upsert_sustainability_preference_profiles",
            [
                {
                    "client_id": "CIF_SG_000184",
                    "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                    "preference_framework": "LOTUS_SUSTAINABILITY_V1",
                    "preference_code": "MIN_SUSTAINABLE_ALLOCATION",
                    "effective_from": "2026-04-01",
                    "preference_version": "1",
                }
            ],
            [
                "client_id",
                "portfolio_id",
                "preference_framework",
                "preference_code",
                "effective_from",
                "preference_version",
            ],
            [
                "mandate_id",
                "preference_status",
                "preference_source",
                "minimum_allocation",
                "maximum_allocation",
                "applies_to_asset_classes",
                "exclusion_codes",
                "positive_tilt_codes",
                "effective_to",
                "source_system",
                "source_record_id",
                "observed_at",
                "quality_status",
            ],
        ),
        (
            "upsert_benchmark_definitions",
            [
                {
                    "benchmark_id": "BMK_001",
                    "benchmark_currency": "USD",
                    "effective_from": "2026-01-01",
                }
            ],
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
            [
                {
                    "index_id": "IDX_001",
                    "index_currency": "USD",
                    "effective_from": "2026-01-01",
                }
            ],
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
            [
                {
                    "series_id": "SER_001",
                    "index_id": "IDX_001",
                    "series_date": "2026-01-01",
                    "series_currency": "USD",
                }
            ],
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
            [
                {
                    "series_id": "SER_001",
                    "index_id": "IDX_001",
                    "series_date": "2026-01-01",
                    "series_currency": "USD",
                }
            ],
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
            [
                {
                    "series_id": "SER_001",
                    "benchmark_id": "BMK_001",
                    "series_date": "2026-01-01",
                    "series_currency": "USD",
                }
            ],
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
                    "series_currency": "USD",
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
async def test_reference_data_upsert_methods_delegate_to_single_table_unit_of_work(
    method_name: str,
    records: list[dict[str, str]],
    conflict_columns: list[str],
    update_columns: list[str],
) -> None:
    db = AsyncMock(spec=AsyncSession)
    service = ReferenceDataIngestionService(db)
    service._commit_upsert_many = AsyncMock()  # type: ignore[method-assign]

    await getattr(service, method_name)(records)

    service._commit_upsert_many.assert_awaited_once()
    assert service._commit_upsert_many.await_args.kwargs["records"] == records
    assert service._commit_upsert_many.await_args.kwargs["conflict_columns"] == conflict_columns
    assert service._commit_upsert_many.await_args.kwargs["update_columns"] == update_columns


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


@pytest.mark.asyncio
async def test_upsert_source_batch_commits_once_after_all_operations_stage() -> None:
    db = AsyncMock(spec=AsyncSession)
    service = ReferenceDataIngestionService(db)
    service._upsert_many = AsyncMock()  # type: ignore[method-assign]
    operations = [
        ReferenceDataUpsertOperation(
            model=object,
            records=[{"id": "benchmark"}],
            conflict_columns=["id"],
            update_columns=["name"],
        ),
        ReferenceDataUpsertOperation(
            model=object,
            records=[{"id": "index"}],
            conflict_columns=["id"],
            update_columns=["name"],
        ),
    ]

    await service.upsert_source_batch(operations)

    assert service._upsert_many.await_count == 2
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_upsert_source_batch_rolls_back_when_later_operation_fails() -> None:
    db = AsyncMock(spec=AsyncSession)
    service = ReferenceDataIngestionService(db)
    failure = RuntimeError("second reference table failed")
    service._upsert_many = AsyncMock(side_effect=[None, failure])  # type: ignore[method-assign]
    operations = [
        ReferenceDataUpsertOperation(
            model=object,
            records=[{"id": "benchmark"}],
            conflict_columns=["id"],
            update_columns=["name"],
        ),
        ReferenceDataUpsertOperation(
            model=object,
            records=[{"id": "index"}],
            conflict_columns=["id"],
            update_columns=["name"],
        ),
    ]

    with pytest.raises(RuntimeError, match="second reference table failed"):
        await service.upsert_source_batch(operations)

    assert service._upsert_many.await_count == 2
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_source_batch_rolls_back_when_first_operation_fails() -> None:
    db = AsyncMock(spec=AsyncSession)
    service = ReferenceDataIngestionService(db)
    service._upsert_many = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("first reference table failed")
    )

    with pytest.raises(RuntimeError, match="first reference table failed"):
        await service.upsert_source_batch(
            [
                ReferenceDataUpsertOperation(
                    model=object,
                    records=[{"id": "benchmark"}],
                    conflict_columns=["id"],
                    update_columns=["name"],
                )
            ]
        )

    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


def test_get_reference_data_ingestion_service_wraps_db_session() -> None:
    db = AsyncMock(spec=AsyncSession)

    service = get_reference_data_ingestion_service(db)  # type: ignore[arg-type]

    assert isinstance(service, ReferenceDataIngestionService)
    assert service._db is db


@pytest.mark.asyncio
async def test_upsert_model_portfolio_definitions_normalizes_base_currency() -> None:
    db = AsyncMock(spec=AsyncSession)
    service = ReferenceDataIngestionService(db)

    await service.upsert_model_portfolio_definitions(
        [
            {
                "model_portfolio_id": "MODEL_SG_BALANCED_DPM",
                "model_portfolio_version": "2026.03",
                "display_name": "Singapore Balanced DPM Model",
                "base_currency": " sgd ",
                "risk_profile": "balanced",
                "mandate_type": "discretionary",
                "approval_status": "approved",
                "effective_from": "2026-03-25",
            }
        ]
    )

    compiled_params = db.execute.await_args.args[0].compile().params
    assert compiled_params["base_currency_m0"] == "SGD"
    db.commit.assert_awaited_once()


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
async def test_upsert_benchmark_definitions_normalizes_benchmark_currency() -> None:
    db = AsyncMock(spec=AsyncSession)
    service = ReferenceDataIngestionService(db)

    await service.upsert_benchmark_definitions(
        [
            {
                "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
                "benchmark_name": "Global Balanced 60/40 Total Return",
                "benchmark_type": "composite",
                "benchmark_currency": " usd ",
                "return_convention": "total_return_index",
                "effective_from": "2025-01-01",
            }
        ]
    )

    compiled_params = db.execute.await_args.args[0].compile().params
    assert compiled_params["benchmark_currency_m0"] == "USD"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "record", "compiled_param"),
    [
        (
            "upsert_indices",
            {
                "index_id": "IDX_GLOBAL_EQUITY_TR",
                "index_name": "Global Equity Total Return",
                "index_currency": " usd ",
                "effective_from": "2026-01-01",
            },
            "index_currency_m0",
        ),
        (
            "upsert_index_price_series",
            {
                "series_id": "series_idx_global_equity_price",
                "index_id": "IDX_GLOBAL_EQUITY_TR",
                "series_date": "2026-01-02",
                "index_price": "4567.1234000000",
                "series_currency": " usd ",
                "value_convention": "official_close",
            },
            "series_currency_m0",
        ),
        (
            "upsert_index_return_series",
            {
                "series_id": "series_idx_global_equity_return",
                "index_id": "IDX_GLOBAL_EQUITY_TR",
                "series_date": "2026-01-02",
                "index_return": "-0.0150000000",
                "return_period": "1d",
                "return_convention": "total_return_index",
                "series_currency": " usd ",
            },
            "series_currency_m0",
        ),
        (
            "upsert_benchmark_return_series",
            {
                "series_id": "series_bmk_global_balanced_return",
                "benchmark_id": "BMK_GLOBAL_BALANCED_60_40",
                "series_date": "2026-01-02",
                "benchmark_return": "-0.0065000000",
                "return_period": "1d",
                "return_convention": "total_return_index",
                "series_currency": " usd ",
            },
            "series_currency_m0",
        ),
        (
            "upsert_risk_free_series",
            {
                "series_id": "rf_usd_sofr_3m",
                "risk_free_curve_id": "USD_SOFR_3M",
                "series_date": "2026-01-02",
                "value": "0.0350000000",
                "value_convention": "annualized_rate",
                "series_currency": " usd ",
            },
            "series_currency_m0",
        ),
    ],
)
async def test_reference_market_series_upserts_normalize_currency(
    method_name: str, record: dict[str, object], compiled_param: str
) -> None:
    db = AsyncMock(spec=AsyncSession)
    service = ReferenceDataIngestionService(db)

    await getattr(service, method_name)([record])

    compiled_params = db.execute.await_args.args[0].compile().params
    assert compiled_params[compiled_param] == "USD"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "record", "compiled_param", "expected_currency"),
    [
        (
            "upsert_client_tax_rule_sets",
            {
                "client_id": "CIF_SG_000184",
                "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                "rule_set_id": "TAX_RULES_SG_2026",
                "tax_year": 2026,
                "jurisdiction_code": "SG",
                "rule_code": "US_DIVIDEND_WITHHOLDING",
                "rule_category": "WITHHOLDING",
                "rule_source": "bank_tax_reference",
                "threshold_amount": "250000.0000",
                "threshold_currency": " sgd ",
                "effective_from": "2026-04-01",
            },
            "threshold_currency_m0",
            "SGD",
        ),
        (
            "upsert_client_income_needs_schedules",
            {
                "client_id": "CIF_SG_000184",
                "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                "schedule_id": "INCOME_NEED_MONTHLY_001",
                "amount": "25000.0000",
                "currency": " sgd ",
                "frequency": "MONTHLY",
                "start_date": "2026-04-01",
            },
            "currency_m0",
            "SGD",
        ),
        (
            "upsert_liquidity_reserve_requirements",
            {
                "client_id": "CIF_SG_000184",
                "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                "reserve_requirement_id": "RESERVE_MIN_CASH_001",
                "required_amount": "150000.0000",
                "currency": " sgd ",
                "horizon_days": 90,
                "policy_source": "POLICY_DPM_SG_BALANCED_V1",
                "effective_from": "2026-04-01",
            },
            "currency_m0",
            "SGD",
        ),
        (
            "upsert_planned_withdrawal_schedules",
            {
                "client_id": "CIF_SG_000184",
                "portfolio_id": "PB_SG_GLOBAL_BAL_001",
                "withdrawal_schedule_id": "WITHDRAWAL_Q3_001",
                "amount": "50000.0000",
                "currency": " sgd ",
                "scheduled_date": "2026-07-15",
            },
            "currency_m0",
            "SGD",
        ),
    ],
)
async def test_private_banking_amount_currency_upserts_normalize_currency(
    method_name: str,
    record: dict[str, object],
    compiled_param: str,
    expected_currency: str,
) -> None:
    db = AsyncMock(spec=AsyncSession)
    service = ReferenceDataIngestionService(db)

    await getattr(service, method_name)([record])

    compiled_params = db.execute.await_args.args[0].compile().params
    assert compiled_params[compiled_param] == expected_currency
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
                "account_currency": " usd ",
                "lifecycle_status": "ACTIVE",
            }
        ]
    )

    compiled_statement = db.execute.await_args.args[0].compile()
    compiled = str(compiled_statement)
    assert "cash_account_masters" in compiled
    assert "ON CONFLICT (cash_account_id)" in compiled
    assert compiled_statement.params["account_currency_m0"] == "USD"
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
