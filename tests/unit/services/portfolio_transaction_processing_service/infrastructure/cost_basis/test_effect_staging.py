"""Verify transactional outbox staging for cost-processing domain effects."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from portfolio_common.events import event_business_payload
from portfolio_common.outbox_repository import OutboxRepository

from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx import (
    FxContractInstrument,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    TransactionalCostProcessingEffectStager,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.cost_basis import (
    effect_staging as effect_staging_module,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.transaction_mapping import (  # noqa: E501
    booked_transaction,
    foreign_exchange_instrument,
)

pytestmark = pytest.mark.asyncio


def _transaction(*, transaction_type: str = "BUY", epoch: int | None = None) -> BookedTransaction:
    return BookedTransaction(
        transaction_id=f"{transaction_type}-OUTBOX-01",
        portfolio_id="PORT-OUTBOX-01",
        instrument_id="INSTRUMENT-OUTBOX-01",
        security_id="SECURITY-OUTBOX-01",
        transaction_date=datetime(2026, 7, 14, 10, 0, tzinfo=timezone.utc),
        transaction_type=transaction_type,
        quantity=Decimal("10"),
        price=Decimal("25"),
        gross_transaction_amount=Decimal("250"),
        trade_currency="SGD",
        currency="SGD",
        epoch=epoch,
    )


def _fx_contract_instrument() -> FxContractInstrument:
    return FxContractInstrument(
        security_id="FX-CONTRACT-01",
        name="FX CONTRACT USD/SGD 2026-07-16",
        isin="SYN-FX-FX-CONTRACT-01",
        currency="USD",
        product_type="FX_CONTRACT",
        asset_class="FX",
        maturity_date=date(2026, 7, 16),
        portfolio_id="PORT-OUTBOX-01",
        trade_date=date(2026, 7, 14),
        pair_base_currency="USD",
        pair_quote_currency="SGD",
        buy_currency="USD",
        sell_currency="SGD",
        buy_amount=Decimal("1000"),
        sell_amount=Decimal("1280"),
        contract_rate=Decimal("1.28"),
    )


@pytest.mark.parametrize("epoch", [None, 7])
async def test_stage_processed_transaction_preserves_payload_and_epoch(epoch: int | None) -> None:
    transaction = _transaction(epoch=epoch)
    outbox = AsyncMock(spec=OutboxRepository)
    stager = TransactionalCostProcessingEffectStager(outbox)

    await stager.stage_processed_transactions(
        [transaction],
        correlation_id="corr-outbox-01",
    )

    expected_event = booked_transaction.to_transaction_event(
        transaction,
        correlation_id=None,
        traceparent=None,
    )
    outbox.create_outbox_event.assert_awaited_once_with(
        aggregate_type="ProcessedTransaction",
        aggregate_id="PORT-OUTBOX-01",
        event_type="ProcessedTransactionPersisted",
        topic="transactions.cost.processed",
        payload=event_business_payload(expected_event, mode="json"),
        correlation_id="corr-outbox-01",
    )


@pytest.mark.parametrize(
    ("transaction_type", "counter_name"),
    [("BUY", "BUY_LIFECYCLE_STAGE_TOTAL"), ("SELL", "SELL_LIFECYCLE_STAGE_TOTAL")],
)
async def test_stage_processed_transaction_records_existing_lifecycle_metric(
    monkeypatch: pytest.MonkeyPatch,
    transaction_type: str,
    counter_name: str,
) -> None:
    counter = MagicMock()
    monkeypatch.setattr(effect_staging_module, counter_name, counter)
    stager = TransactionalCostProcessingEffectStager(AsyncMock(spec=OutboxRepository))

    await stager.stage_processed_transactions(
        [_transaction(transaction_type=transaction_type)],
        correlation_id="corr-metric-01",
    )

    counter.labels.assert_called_once_with("emit_outbox", "success")
    counter.labels.return_value.inc.assert_called_once_with()


async def test_stage_non_trade_transaction_does_not_record_trade_lifecycle_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buy_counter = MagicMock()
    sell_counter = MagicMock()
    monkeypatch.setattr(effect_staging_module, "BUY_LIFECYCLE_STAGE_TOTAL", buy_counter)
    monkeypatch.setattr(effect_staging_module, "SELL_LIFECYCLE_STAGE_TOTAL", sell_counter)
    stager = TransactionalCostProcessingEffectStager(AsyncMock(spec=OutboxRepository))

    await stager.stage_processed_transactions(
        [_transaction(transaction_type="ADJUSTMENT")],
        correlation_id="corr-adjustment-01",
    )

    buy_counter.labels.assert_not_called()
    sell_counter.labels.assert_not_called()


async def test_stage_fx_contract_instrument_preserves_integration_contract() -> None:
    instrument = _fx_contract_instrument()
    outbox = AsyncMock(spec=OutboxRepository)
    stager = TransactionalCostProcessingEffectStager(outbox)

    await stager.stage_instrument_updates(
        [instrument],
        correlation_id="corr-instrument-01",
    )

    expected_event = foreign_exchange_instrument.to_fx_contract_instrument_event(instrument)
    outbox.create_outbox_event.assert_awaited_once_with(
        aggregate_type="Instrument",
        aggregate_id="FX-CONTRACT-01",
        event_type="InstrumentUpserted",
        topic="instruments.received",
        payload=expected_event.model_dump(mode="json"),
        correlation_id="corr-instrument-01",
    )
