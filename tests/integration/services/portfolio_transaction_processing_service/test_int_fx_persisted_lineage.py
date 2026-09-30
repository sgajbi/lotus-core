"""PostgreSQL proof for final-row foreign-exchange calculation lineage."""

from dataclasses import fields
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.domain.calculation_lineage import calculation_lineage_binds_output
from portfolio_common.domain.transaction import (
    TRANSACTION_PAYLOAD_MATERIAL_FIELDS,
    transaction_payload_fingerprint,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.portfolio_transaction_processing_service.app.application.foreign_exchange_processing import (  # noqa: E501
    book_foreign_exchange_transaction,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx import (
    fx_booked_transaction_output_payload,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    SqlAlchemyCostBasisTransactionRepository,
)
from tests.test_support.transaction_processing import portfolio_record

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration_db,
    pytest.mark.db_direct,
    pytest.mark.regression,
]


def _fx_transaction(*, source_system: str | None) -> BookedTransaction:
    return BookedTransaction(
        transaction_id="FX-LINEAGE-REPROCESS-001",
        portfolio_id="PORT-FX-LINEAGE-001",
        tenant_id="tenant-test",
        instrument_id="FXC-EURUSD-LINEAGE-001",
        security_id="FXC-EURUSD-LINEAGE-001",
        transaction_date=datetime(2026, 4, 1, 9, 0, tzinfo=UTC),
        settlement_date=datetime(2026, 7, 1, 9, 0, tzinfo=UTC),
        transaction_type="FX_FORWARD",
        component_type="FX_CONTRACT_OPEN",
        component_id="FX-COMP-LINEAGE-001",
        linked_component_ids=("FX-COMP-BUY-001", "FX-COMP-SELL-001"),
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=Decimal("1095000"),
        trade_currency="USD",
        currency="USD",
        pair_base_currency="EUR",
        pair_quote_currency="USD",
        fx_rate_quote_convention="QUOTE_PER_BASE",
        buy_currency="USD",
        sell_currency="EUR",
        buy_amount=Decimal("1095000"),
        sell_amount=Decimal("1000000"),
        contract_rate=Decimal("1.095"),
        economic_event_id="EVT-FX-LINEAGE-001",
        linked_transaction_group_id="LTG-FX-LINEAGE-001",
        calculation_policy_id="FX_DEFAULT_POLICY",
        calculation_policy_version="1.0.0",
        fx_contract_id="FXC-EURUSD-LINEAGE-001",
        spot_exposure_model="NONE",
        fx_realized_pnl_mode="NONE",
        source_system=source_system,
    )


async def test_fx_reprocessing_receipt_binds_optional_value_retained_by_conflict_update(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    existing = _fx_transaction(source_system="EXISTING_BOOKING_LEDGER")
    async_db_session.add(portfolio_record(existing.portfolio_id))
    async_db_session.add(
        DBTransaction(
            **{
                field.name: value
                for field in fields(existing)
                if field.name in DBTransaction.__table__.columns
                and field.name != "calculation_lineage"
                and (value := getattr(existing, field.name)) is not None
            }
        )
    )
    await async_db_session.commit()

    result = await book_foreign_exchange_transaction(
        transaction=_fx_transaction(source_system=None),
        transaction_persistence=SqlAlchemyCostBasisTransactionRepository(async_db_session),
    )
    durable_row = (
        (
            await async_db_session.execute(
                select(*DBTransaction.__table__.columns).where(
                    DBTransaction.transaction_id == result.transaction.transaction_id
                )
            )
        )
        .mappings()
        .one()
    )

    assert durable_row["source_system"] == "EXISTING_BOOKING_LEDGER"
    assert result.transaction.source_system == durable_row["source_system"]
    assert durable_row["payload_fingerprint"] == transaction_payload_fingerprint(
        {
            field_name: durable_row[field_name]
            for field_name in TRANSACTION_PAYLOAD_MATERIAL_FIELDS
            if field_name in DBTransaction.__table__.columns
        }
        | {
            "transaction_fx_rate": durable_row["transaction_fx_rate"],
            "transaction_fx_rate_origin": durable_row["transaction_fx_rate_origin"],
        }
    )
    assert result.transaction.calculation_lineage is not None
    assert durable_row["calculation_lineage"] == (
        result.transaction.calculation_lineage.lineage_payload()
    )
    assert calculation_lineage_binds_output(
        result.transaction.calculation_lineage,
        output_payload=fx_booked_transaction_output_payload(result.transaction),
    )


def _generated_cash_leg(
    *,
    source_system: str | None,
    gross_transaction_amount: Decimal,
    transaction_fx_rate: Decimal = Decimal("2"),
) -> BookedTransaction:
    return BookedTransaction(
        transaction_id="BUY-LINEAGE-001-CASHLEG",
        portfolio_id="PORT-FX-LINEAGE-001",
        tenant_id="tenant-test",
        instrument_id="CASH-USD",
        security_id="CASH-USD",
        transaction_type="ADJUSTMENT",
        transaction_date=datetime(2026, 4, 1, 9, 0, tzinfo=UTC),
        quantity=Decimal(0),
        price=Decimal(1),
        gross_transaction_amount=gross_transaction_amount,
        trade_currency="USD",
        currency="USD",
        cash_entry_mode="AUTO_GENERATE",
        originating_transaction_id="BUY-LINEAGE-001",
        originating_transaction_type="BUY",
        link_type="BUY_TO_CASH",
        source_system=source_system,
        transaction_fx_rate=transaction_fx_rate,
        transaction_fx_rate_origin="SOURCE_BOOKED",
    )


async def test_generated_child_fingerprint_uses_post_upsert_durable_economics(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    existing = _generated_cash_leg(
        source_system="EXISTING_BOOKING_LEDGER",
        gross_transaction_amount=Decimal("1080000"),
    )
    async_db_session.add(portfolio_record(existing.portfolio_id))
    preloaded_record = DBTransaction(
        **{
            field.name: value
            for field in fields(existing)
            if field.name in DBTransaction.__table__.columns
            and field.name != "calculation_lineage"
            and (value := getattr(existing, field.name)) is not None
        }
    )
    async_db_session.add(preloaded_record)
    await async_db_session.commit()

    result = await SqlAlchemyCostBasisTransactionRepository(
        async_db_session
    ).upsert_generated_booked_transaction(
        _generated_cash_leg(
            source_system=None,
            gross_transaction_amount=Decimal("1095000"),
        )
    )
    durable_row = (
        (
            await async_db_session.execute(
                select(*DBTransaction.__table__.columns).where(
                    DBTransaction.transaction_id == result.transaction_id
                )
            )
        )
        .mappings()
        .one()
    )

    assert durable_row["source_system"] == "EXISTING_BOOKING_LEDGER"
    assert durable_row["gross_transaction_amount"] == Decimal("1095000")
    assert result.source_system == durable_row["source_system"]
    assert result.gross_transaction_amount == durable_row["gross_transaction_amount"]
    assert durable_row["payload_fingerprint"] == transaction_payload_fingerprint(
        {
            field_name: durable_row[field_name]
            for field_name in TRANSACTION_PAYLOAD_MATERIAL_FIELDS
            if field_name in DBTransaction.__table__.columns
        }
        | {
            "transaction_fx_rate": durable_row["transaction_fx_rate"],
            "transaction_fx_rate_origin": durable_row["transaction_fx_rate_origin"],
        }
    )

    prior_fingerprint = durable_row["payload_fingerprint"]
    await SqlAlchemyCostBasisTransactionRepository(
        async_db_session
    ).upsert_generated_booked_transaction(
        _generated_cash_leg(
            source_system=None,
            gross_transaction_amount=Decimal("1095000"),
            transaction_fx_rate=Decimal("2.5"),
        )
    )
    refreshed = (
        (
            await async_db_session.execute(
                select(*DBTransaction.__table__.columns).where(
                    DBTransaction.transaction_id == result.transaction_id
                )
            )
        )
        .mappings()
        .one()
    )
    assert refreshed["payload_fingerprint"] != prior_fingerprint
    assert refreshed["payload_fingerprint"] == transaction_payload_fingerprint(
        {
            field_name: refreshed[field_name]
            for field_name in TRANSACTION_PAYLOAD_MATERIAL_FIELDS
            if field_name in DBTransaction.__table__.columns
        }
        | {
            "transaction_fx_rate": refreshed["transaction_fx_rate"],
            "transaction_fx_rate_origin": refreshed["transaction_fx_rate_origin"],
        }
    )
