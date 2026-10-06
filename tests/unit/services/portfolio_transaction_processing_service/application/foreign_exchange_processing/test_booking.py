"""Application tests for validated foreign-exchange transaction booking."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from portfolio_common.domain.calculation_lineage import (
    calculation_lineage_binds_output,
    canonical_content_hash,
)
from portfolio_common.domain.transaction import transaction_payload_fingerprint
from portfolio_common.domain.transaction.fx_source_presence import FX_ORIGINAL_PNL_FIELDS

from src.services.portfolio_transaction_processing_service.app.application import (
    foreign_exchange_processing,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx import (
    FX_BASELINE_CALCULATION_ALGORITHM_ID,
    build_fx_processed_transaction,
    fx_booked_transaction_output_payload,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx.persisted_return import (  # noqa: E501
    FxBookingContext,
    FxPersistenceWitness,
    fx_source_material,
    qualify_fx_raw_source,
)
from src.services.portfolio_transaction_processing_service.app.ports import (
    ForeignExchangeTransactionPersistencePort,
)

pytestmark = pytest.mark.asyncio

book_foreign_exchange_transaction = foreign_exchange_processing.book_foreign_exchange_transaction


def _retention_witness(before: BookedTransaction, raw_source: BookedTransaction | None = None):
    if before.fx_realized_pnl_mode == "NONE":
        return FxPersistenceWitness(before, None, None)
    material = fx_source_material(raw_source or before)
    facts = qualify_fx_raw_source(
        raw=material,
        transaction=before,
        stored_fingerprint=transaction_payload_fingerprint(material),
        raw_event_id=17,
        raw_payload_hash=canonical_content_hash(material),
    )
    return FxPersistenceWitness(before, facts.original_pnl, facts)


async def test_booking_rebinds_exact_prewrite_creation_timestamp_when_omitted() -> None:
    timestamp = datetime(2026, 4, 1, 8, 0, tzinfo=UTC)
    incoming = _foreign_exchange_transaction(fx_realized_pnl_mode="NONE", created_at=None)
    before = replace(incoming, created_at=timestamp)
    persistence = _transaction_persistence()
    persistence.load_fx_retention_witness.return_value = _retention_witness(before)
    persistence.upsert_booked_transaction.side_effect = lambda row: replace(
        row, created_at=timestamp
    )
    result = await book_foreign_exchange_transaction(
        transaction=incoming, transaction_persistence=persistence
    )
    assert persistence.upsert_booked_transaction.await_count == 2
    persistence.load_fx_creation_timestamp.assert_not_awaited()
    assert result.transaction.created_at == timestamp
    assert calculation_lineage_binds_output(
        result.transaction.calculation_lineage,
        output_payload=fx_booked_transaction_output_payload(result.transaction),
    )


@pytest.mark.parametrize("witness_available", [False, True])
async def test_booking_rejects_invented_creation_timestamp(witness_available: bool) -> None:
    incoming = _foreign_exchange_transaction(fx_realized_pnl_mode="NONE", created_at=None)
    persistence = _transaction_persistence()
    if witness_available:
        persistence.load_fx_retention_witness.return_value = _retention_witness(
            replace(incoming, created_at=datetime(2026, 4, 1, 8, 0, tzinfo=UTC))
        )
    persistence.upsert_booked_transaction.side_effect = lambda row: replace(
        row, created_at=datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
    )
    with pytest.raises(
        ValueError, match="invented retained creation timestamp|changed admitted material"
    ):
        await book_foreign_exchange_transaction(
            transaction=incoming, transaction_persistence=persistence
        )
    assert persistence.upsert_booked_transaction.await_count == 1


async def test_booking_rejects_changed_explicit_creation_timestamp() -> None:
    incoming = _foreign_exchange_transaction(
        fx_realized_pnl_mode="NONE", created_at=datetime(2026, 4, 1, 8, 0, tzinfo=UTC)
    )
    persistence = _transaction_persistence()
    persistence.load_fx_retention_witness.return_value = _retention_witness(incoming)
    persistence.upsert_booked_transaction.side_effect = lambda row: replace(
        row, created_at=datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
    )
    with pytest.raises(ValueError, match="changed admitted material"):
        await book_foreign_exchange_transaction(
            transaction=incoming, transaction_persistence=persistence
        )
    assert persistence.upsert_booked_transaction.await_count == 1
    persistence.load_fx_creation_timestamp.assert_not_awaited()


@pytest.mark.parametrize(
    "timestamp",
    [
        None,
        "2026-04-01T08:00:00Z",
        datetime(2026, 4, 1, 8, 0),
        datetime(2026, 4, 1, 8, 0, tzinfo=timezone(timedelta(hours=8))),
    ],
)
async def test_booking_refuses_invalid_server_creation_timestamp(timestamp) -> None:
    incoming = _foreign_exchange_transaction(fx_realized_pnl_mode="NONE", created_at=None)
    persistence = _transaction_persistence()
    persistence.load_fx_creation_timestamp.return_value = timestamp
    with pytest.raises(ValueError, match="aware UTC datetime"):
        await book_foreign_exchange_transaction(
            transaction=incoming, transaction_persistence=persistence
        )
    persistence.upsert_booked_transaction.assert_not_awaited()


async def test_booking_binds_fresh_server_creation_timestamp_without_retention_witness() -> None:
    incoming = _foreign_exchange_transaction(fx_realized_pnl_mode="NONE", created_at=None)
    persistence = _transaction_persistence()
    result = await book_foreign_exchange_transaction(
        transaction=incoming, transaction_persistence=persistence
    )
    persistence.load_fx_creation_timestamp.assert_awaited_once_with()
    assert result.transaction.created_at == persistence.load_fx_creation_timestamp.return_value
    assert calculation_lineage_binds_output(
        result.transaction.calculation_lineage,
        output_payload=fx_booked_transaction_output_payload(result.transaction),
    )


@pytest.mark.parametrize("field_name", ["transaction_date", "settlement_date"])
@pytest.mark.parametrize(
    "bad_value", [None, datetime(2026, 4, 1, 9, 0), datetime(2026, 4, 1, 10, 0, tzinfo=UTC)]
)
async def test_typed_raw_date_projection_cannot_substitute_original_instant(field_name, bad_value):
    before = _foreign_exchange_transaction(tenant_id="tenant-fx")
    identity = fx_source_material(before)
    raw = dict(identity)
    raw[field_name] = bad_value.isoformat() if isinstance(bad_value, datetime) else bad_value
    with pytest.raises(ValueError, match="original presence or aware instant"):
        qualify_fx_raw_source(
            raw=raw,
            identity_source=identity,
            transaction=before,
            stored_fingerprint=transaction_payload_fingerprint(identity),
            raw_event_id=17,
            raw_payload_hash=canonical_content_hash(raw),
        )


@pytest.mark.parametrize("failure", ["hash", "non_time", "absent", "null_to_value"])
async def test_typed_raw_projection_preserves_integrity_and_non_time_facts(failure):
    before = _foreign_exchange_transaction(tenant_id="tenant-fx", settlement_date=None)
    raw = fx_source_material(before)
    identity = dict(raw)
    raw_hash = canonical_content_hash(raw)
    if failure == "hash":
        raw_hash = "wrong-raw-hash"
    elif failure == "non_time":
        identity["source_system"] = "SUBSTITUTED"
    elif failure == "absent":
        raw.pop("settlement_date")
        raw_hash = canonical_content_hash(raw)
    else:
        identity["settlement_date"] = datetime(2026, 7, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="provenance|non-time facts|presence or aware instant"):
        qualify_fx_raw_source(
            raw=raw,
            identity_source=identity,
            transaction=before,
            stored_fingerprint=transaction_payload_fingerprint(identity),
            raw_event_id=17,
            raw_payload_hash=raw_hash,
        )


@pytest.mark.parametrize("mode", ["NONE", "UPSTREAM_PROVIDED"])
@pytest.mark.parametrize("processed", [False, True])
async def test_retention_preserves_original_missing_values_and_exact_source_rate(mode, processed):
    raw = _foreign_exchange_transaction(
        tenant_id="tenant-fx",
        source_system="ORIGINAL",
        fx_realized_pnl_mode=mode,
        realized_capital_pnl_local=None,
        realized_total_pnl_local=None,
        realized_capital_pnl_base=Decimal("0.000"),
        realized_total_pnl_base=None,
        transaction_fx_rate=Decimal("1.123456789"),
        transaction_fx_rate_origin="SOURCE_BOOKED",
    )
    before = build_fx_processed_transaction(raw) if processed else raw
    incoming = replace(before, source_system=None)
    persistence = _transaction_persistence()
    persistence.load_fx_retention_witness.return_value = _retention_witness(before, raw)
    persistence.upsert_booked_transaction.side_effect = lambda row: replace(
        row, source_system="ORIGINAL"
    )
    result = await book_foreign_exchange_transaction(
        transaction=incoming,
        transaction_persistence=persistence,
        booking_context=FxBookingContext(initial_publication=not processed, admitted_epoch=None),
    )
    original = {
        name: getattr(raw if mode == "UPSTREAM_PROVIDED" else incoming, name)
        for name in FX_ORIGINAL_PNL_FIELDS
    }
    expected = build_fx_processed_transaction(
        replace(incoming, source_system="ORIGINAL"), original_pnl=original
    )
    assert result.transaction == expected
    assert persistence.upsert_booked_transaction.await_count == 2
    assert result.transaction.transaction_fx_rate == raw.transaction_fx_rate
    assert result.transaction.transaction_fx_rate_origin == "SOURCE_BOOKED"
    if mode == "UPSTREAM_PROVIDED":
        assert (
            expected.calculation_lineage
            != build_fx_processed_transaction(result.transaction).calculation_lineage
        )


@pytest.mark.parametrize(
    "damage",
    [
        {"quantity": Decimal("1")},
        {"gross_transaction_amount": Decimal("1095001")},
        {"transaction_fx_rate": Decimal("1.2")},
        {"transaction_fx_rate_origin": "REFERENCE"},
        {"realized_fx_pnl_local": Decimal("1251")},
        {"tenant_id": "foreign"},
        {"source_system": "INVENTED"},
    ],
)
async def test_first_return_rejects_mutation_even_with_a_fresh_valid_receipt(damage):
    transaction = _foreign_exchange_transaction(tenant_id="tenant-fx", source_system="ORIGINAL")
    persistence = _transaction_persistence()
    persistence.load_fx_retention_witness.return_value = _retention_witness(transaction)
    persistence.upsert_booked_transaction.side_effect = lambda row: build_fx_processed_transaction(
        replace(row, **damage)
    )
    with pytest.raises(ValueError, match="changed admitted material"):
        await book_foreign_exchange_transaction(
            transaction=transaction,
            transaction_persistence=persistence,
            booking_context=FxBookingContext(True, None),
        )
    assert persistence.upsert_booked_transaction.await_count == 1


@pytest.mark.parametrize(
    "damage", [{"source_system": "OTHER"}, {"gross_transaction_amount": Decimal("1095001")}]
)
async def test_second_return_requires_exact_rebound_row_and_receipt(damage):
    before = _foreign_exchange_transaction(source_system="ORIGINAL")
    persistence = _transaction_persistence()
    persistence.load_fx_retention_witness.return_value = _retention_witness(before)

    def persist(row):
        if persistence.upsert_booked_transaction.await_count == 1:
            return replace(row, source_system="ORIGINAL")
        return build_fx_processed_transaction(replace(row, **damage))

    persistence.upsert_booked_transaction.side_effect = persist
    with pytest.raises(RuntimeError, match="qualified final receipt"):
        await book_foreign_exchange_transaction(
            transaction=replace(before, source_system=None),
            transaction_persistence=persistence,
            booking_context=FxBookingContext(True, None),
        )
    assert persistence.upsert_booked_transaction.await_count == 2


@pytest.mark.parametrize(
    "context",
    [None, FxBookingContext(False, None), FxBookingContext(True, 0), FxBookingContext(True, 3)],
)
async def test_unprocessed_upstream_raw_requires_actual_initial_admission(context):
    transaction = _foreign_exchange_transaction()
    persistence = _transaction_persistence()
    persistence.load_fx_retention_witness.return_value = _retention_witness(transaction)
    with pytest.raises(ValueError, match="admitted epoch|first-publication admission"):
        await book_foreign_exchange_transaction(
            transaction=transaction, transaction_persistence=persistence, booking_context=context
        )
    persistence.upsert_booked_transaction.assert_not_awaited()


async def test_initial_upstream_missing_is_not_an_explicit_zero():
    raw = _foreign_exchange_transaction(realized_capital_pnl_local=None)
    persistence = _transaction_persistence()
    persistence.load_fx_retention_witness.return_value = _retention_witness(raw)
    with pytest.raises(ValueError, match="admitted P&L differs"):
        await book_foreign_exchange_transaction(
            transaction=replace(raw, realized_capital_pnl_local=Decimal(0)),
            transaction_persistence=persistence,
            booking_context=FxBookingContext(True, None),
        )
    persistence.upsert_booked_transaction.assert_not_awaited()


async def test_upstream_without_raw_witness_refuses_before_write():
    transaction = _foreign_exchange_transaction()
    persistence = _transaction_persistence()
    persistence.load_fx_retention_witness.return_value = FxPersistenceWitness(
        transaction, None, None
    )
    with pytest.raises(ValueError, match="original upstream source"):
        await book_foreign_exchange_transaction(
            transaction=transaction,
            transaction_persistence=persistence,
            booking_context=FxBookingContext(True, None),
        )
    persistence.upsert_booked_transaction.assert_not_awaited()


@pytest.mark.parametrize("damage", [None, "tenant", "epoch"])
async def test_explicit_handoff_is_not_reloaded_and_cannot_cross_admission(damage):
    transaction = _foreign_exchange_transaction(tenant_id="tenant-fx")
    witness = _retention_witness(transaction)
    if damage == "tenant":
        witness = replace(witness, durable_before=replace(transaction, tenant_id="foreign"))
    elif damage == "epoch":
        witness = replace(witness, admitted_epoch=3)
    persistence = _transaction_persistence()
    context = FxBookingContext(True, None, witness)
    if damage is None:
        result = await book_foreign_exchange_transaction(
            transaction=transaction,
            transaction_persistence=persistence,
            booking_context=context,
        )
        assert result.transaction.calculation_lineage is not None
        persistence.upsert_booked_transaction.assert_awaited_once()
    else:
        with pytest.raises(ValueError, match="owner mismatch|different admitted epoch"):
            await book_foreign_exchange_transaction(
                transaction=transaction,
                transaction_persistence=persistence,
                booking_context=context,
            )
        persistence.upsert_booked_transaction.assert_not_awaited()
    persistence.load_fx_retention_witness.assert_not_awaited()


def _transaction_persistence() -> AsyncMock:
    persistence = AsyncMock(spec=ForeignExchangeTransactionPersistencePort)
    persistence.load_fx_retention_witness.return_value = None
    persistence.load_fx_creation_timestamp.return_value = datetime(2026, 4, 1, 8, 0, tzinfo=UTC)
    persistence.upsert_booked_transaction.side_effect = lambda transaction: transaction
    return persistence


def _foreign_exchange_transaction(**updates: object) -> BookedTransaction:
    transaction = BookedTransaction(
        transaction_id="FX-OPEN-001",
        portfolio_id="PORT-FX-1",
        instrument_id="FXC-EURUSD-001",
        security_id="FXC-EURUSD-001",
        transaction_date=datetime(2026, 4, 1, 9, 0, tzinfo=UTC),
        created_at=datetime(2026, 4, 1, 8, 0, tzinfo=UTC),
        settlement_date=datetime(2026, 7, 1, 9, 0, tzinfo=UTC),
        transaction_type="FX_FORWARD",
        component_type="FX_CONTRACT_OPEN",
        component_id="FX-COMP-OPEN-001",
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
        economic_event_id="EVT-FX-001",
        linked_transaction_group_id="LTG-FX-001",
        calculation_policy_id="FX_DEFAULT_POLICY",
        calculation_policy_version="1.0.0",
        fx_contract_id="FXC-2026-0001",
        spot_exposure_model="NONE",
        fx_realized_pnl_mode="UPSTREAM_PROVIDED",
        realized_capital_pnl_local=Decimal(0),
        realized_fx_pnl_local=Decimal("1250"),
        realized_total_pnl_local=Decimal("1250"),
        realized_capital_pnl_base=Decimal(0),
        realized_fx_pnl_base=Decimal("1250"),
        realized_total_pnl_base=Decimal("1250"),
    )
    return replace(transaction, **updates)


async def test_booking_persists_validated_fx_transaction_and_returns_contract_instrument() -> None:
    transaction = _foreign_exchange_transaction(fx_realized_pnl_mode=" upstream_provided ")
    persistence = _transaction_persistence()

    result = await book_foreign_exchange_transaction(
        transaction=transaction,
        transaction_persistence=persistence,
    )

    assert result.transaction.fx_realized_pnl_mode == "UPSTREAM_PROVIDED"
    assert result.transaction.calculation_lineage is not None
    assert (
        result.transaction.calculation_lineage.algorithm_id == FX_BASELINE_CALCULATION_ALGORITHM_ID
    )
    assert calculation_lineage_binds_output(
        result.transaction.calculation_lineage,
        output_payload=fx_booked_transaction_output_payload(result.transaction),
    )
    persistence.upsert_booked_transaction.assert_awaited_once_with(result.transaction)
    assert result.contract_instrument is not None
    assert result.contract_instrument.security_id == "FXC-2026-0001"


async def test_booking_rebinds_lineage_when_conflict_retains_optional_durable_output() -> None:
    persistence = AsyncMock(spec=ForeignExchangeTransactionPersistencePort)
    before = _foreign_exchange_transaction(source_system="EXISTING_BOOKING_LEDGER")
    material = fx_source_material(before)
    facts = qualify_fx_raw_source(
        raw=material,
        transaction=before,
        stored_fingerprint=transaction_payload_fingerprint(material),
        raw_event_id=1,
        raw_payload_hash=canonical_content_hash(material),
    )
    persistence.load_fx_retention_witness.return_value = FxPersistenceWitness(
        before,
        facts.original_pnl,
        facts,
    )

    async def _persist(transaction: BookedTransaction) -> BookedTransaction:
        if persistence.upsert_booked_transaction.await_count == 1:
            return replace(transaction, source_system="EXISTING_BOOKING_LEDGER")
        return transaction

    persistence.upsert_booked_transaction.side_effect = _persist

    result = await book_foreign_exchange_transaction(
        transaction=_foreign_exchange_transaction(source_system=None),
        transaction_persistence=persistence,
        booking_context=FxBookingContext(initial_publication=True, admitted_epoch=None),
    )

    assert persistence.upsert_booked_transaction.await_count == 2
    assert result.transaction.source_system == "EXISTING_BOOKING_LEDGER"
    assert calculation_lineage_binds_output(
        result.transaction.calculation_lineage,
        output_payload=fx_booked_transaction_output_payload(result.transaction),
    )


async def test_booking_returns_no_contract_instrument_for_cash_settlement_component() -> None:
    transaction = _foreign_exchange_transaction(
        component_type="FX_CASH_SETTLEMENT_BUY",
        fx_cash_leg_role="BUY",
        linked_fx_cash_leg_id="FX-CASH-SELL-001",
    )
    persistence = _transaction_persistence()

    result = await book_foreign_exchange_transaction(
        transaction=transaction,
        transaction_persistence=persistence,
    )

    assert result.contract_instrument is None
    persistence.upsert_booked_transaction.assert_awaited_once_with(result.transaction)


async def test_booking_rejects_invalid_fx_transaction_before_persistence() -> None:
    transaction = _foreign_exchange_transaction(buy_currency="USD", sell_currency="USD")
    persistence = _transaction_persistence()

    with pytest.raises(ValueError, match="FX validation failed"):
        await book_foreign_exchange_transaction(
            transaction=transaction,
            transaction_persistence=persistence,
        )

    persistence.upsert_booked_transaction.assert_not_awaited()


async def test_booking_lineage_is_deterministic_and_changes_with_material_fx_output() -> None:
    persistence = _transaction_persistence()
    baseline = _foreign_exchange_transaction()

    first = await book_foreign_exchange_transaction(
        transaction=baseline,
        transaction_persistence=persistence,
    )
    repeated = await book_foreign_exchange_transaction(
        transaction=first.transaction,
        transaction_persistence=persistence,
    )
    changed = await book_foreign_exchange_transaction(
        transaction=replace(
            baseline,
            realized_fx_pnl_local=Decimal("1300"),
            realized_total_pnl_local=Decimal("1300"),
            realized_fx_pnl_base=Decimal("1300"),
            realized_total_pnl_base=Decimal("1300"),
        ),
        transaction_persistence=persistence,
    )

    assert first.transaction.calculation_lineage == repeated.transaction.calculation_lineage
    assert first.transaction.calculation_lineage is not None
    assert changed.transaction.calculation_lineage is not None
    assert (
        first.transaction.calculation_lineage.input_content_hash
        != changed.transaction.calculation_lineage.input_content_hash
    )
    assert (
        first.transaction.calculation_lineage.output_content_hash
        != changed.transaction.calculation_lineage.output_content_hash
    )


@pytest.mark.parametrize("field_name", ["transaction_date", "settlement_date", "created_at"])
async def test_booking_rejects_timezone_ambiguous_fx_lineage_timestamps(
    field_name: str,
) -> None:
    transaction = _foreign_exchange_transaction(**{field_name: datetime(2026, 4, 1, 9, 0)})
    persistence = _transaction_persistence()

    with pytest.raises(ValueError, match=rf"{field_name}.*timezone-aware"):
        await book_foreign_exchange_transaction(
            transaction=transaction,
            transaction_persistence=persistence,
        )

    persistence.upsert_booked_transaction.assert_not_awaited()


async def test_booking_canonicalizes_aware_fx_timestamps_to_the_same_utc_lineage() -> None:
    persistence = _transaction_persistence()
    utc_transaction = _foreign_exchange_transaction(
        transaction_date=datetime(2026, 4, 1, 1, 0, tzinfo=UTC),
        settlement_date=datetime(2026, 7, 1, 1, 0, tzinfo=UTC),
    )
    singapore_transaction = _foreign_exchange_transaction(
        transaction_date=datetime(
            2026,
            4,
            1,
            9,
            0,
            tzinfo=timezone(timedelta(hours=8)),
        ),
        settlement_date=datetime(
            2026,
            7,
            1,
            9,
            0,
            tzinfo=timezone(timedelta(hours=8)),
        ),
    )

    utc_result = await book_foreign_exchange_transaction(
        transaction=utc_transaction,
        transaction_persistence=persistence,
    )
    singapore_result = await book_foreign_exchange_transaction(
        transaction=singapore_transaction,
        transaction_persistence=persistence,
    )

    assert utc_result.transaction.calculation_lineage == (
        singapore_result.transaction.calculation_lineage
    )


@pytest.mark.parametrize(
    ("charge_update", "expected_reason"),
    [
        ({"trade_fee": Decimal("1")}, "FX_025_NON_ZERO_EMBEDDED_FEE:trade_fee"),
        (
            {"trade_fee": Decimal("0"), "brokerage": Decimal("1")},
            "FX_025_NON_ZERO_EMBEDDED_FEE:trade_fee",
        ),
        (
            {"withholding_tax_amount": Decimal("1")},
            "FX_026_NON_ZERO_EMBEDDED_TAX:withholding_tax_amount",
        ),
    ],
)
async def test_booking_rejects_embedded_fx_charge_before_persistence(
    charge_update: dict[str, Decimal],
    expected_reason: str,
) -> None:
    transaction = _foreign_exchange_transaction(**charge_update)
    persistence = _transaction_persistence()

    with pytest.raises(ValueError, match=expected_reason):
        await book_foreign_exchange_transaction(
            transaction=transaction,
            transaction_persistence=persistence,
        )

    persistence.upsert_booked_transaction.assert_not_awaited()
