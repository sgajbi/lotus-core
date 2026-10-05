from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.services.portfolio_transaction_processing_service.app.application.position_history import (
    PositionHistoryProcessingResult,
    PositionHistoryProcessor,
)
from src.services.portfolio_transaction_processing_service.app.domain import (
    BookedTransaction,
    build_transaction_correction_identity,
)
from src.services.portfolio_transaction_processing_service.app.infrastructure.position import (
    PositionHistoryProcessingAdapter,
)
from src.services.portfolio_transaction_processing_service.app.ports.position_history import (
    AdmittedPositionCorrectionGroup,
    MaterializedPositionReceipt,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("admitted", [False, True])
async def test_position_adapter_returns_position_and_replay_outcome(admitted) -> None:
    transaction = BookedTransaction(
        transaction_id="TX-001",
        portfolio_id="PB-001",
        tenant_id="tenant-test",
        instrument_id="INST-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 4, 10, 9, 30, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("25.50"),
        gross_transaction_amount=Decimal("255.00"),
        trade_currency="SGD",
        currency="SGD",
    )
    processor = AsyncMock(spec=PositionHistoryProcessor)
    rebuilt_transaction = replace(transaction, transaction_id="TX-REBUILT", epoch=4)
    processor.process.return_value = PositionHistoryProcessingResult(
        position_record_count=2,
        rebuilt_transactions=(rebuilt_transaction,),
        locked_state_epoch=4,
    )
    adapter = PositionHistoryProcessingAdapter(processor=processor)
    group = (
        AdmittedPositionCorrectionGroup(
            transaction,
            build_transaction_correction_identity(transaction),
            "correction-event",
            None,
            True,
            False,
            (transaction,),
        )
        if admitted
        else None
    )

    result = await adapter.process(
        transaction,
        correlation_id="corr-001",
        traceparent="trace-001",
        rebuild_existing=True,
        admitted_correction=group,
    )

    assert result.position_record_count == 2
    assert result.replay_queued is False
    assert result.cashflow_rebuild_transactions == (rebuilt_transaction,)
    assert result.locked_state_epoch == 4
    processor.process.assert_awaited_once_with(
        transaction, rebuild_existing=True, admitted_correction=group
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("quantity", [Decimal("0"), Decimal("18")])
async def test_position_adapter_preserves_existing_materialization_without_new_records(quantity):
    transaction = BookedTransaction(
        transaction_id="TX-001",
        portfolio_id="PB-001",
        tenant_id="tenant-test",
        instrument_id="INST-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 4, 10, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity=Decimal("10"),
        price=Decimal("25.50"),
        gross_transaction_amount=Decimal("255"),
        trade_currency="SGD",
        currency="SGD",
    )
    receipt = MaterializedPositionReceipt(
        tenant_id="tenant-test",
        portfolio_id=transaction.portfolio_id,
        security_id=transaction.security_id,
        transaction_id=transaction.transaction_id,
        epoch=4,
        quantity=quantity,
    )
    processor = AsyncMock(spec=PositionHistoryProcessor)
    processor.process.return_value = PositionHistoryProcessingResult(
        locked_state_epoch=4,
        processed_transaction_quantity=quantity,
        materialized_receipt=receipt,
    )
    result = await PositionHistoryProcessingAdapter(processor=processor).process(
        transaction, correlation_id=None, traceparent=None
    )
    assert result.position_record_count == 0
    assert result.cashflow_rebuild_transactions == ()
    assert result.materialized_receipt is receipt
    assert result.locked_state_epoch == 4
    assert result.processed_transaction_quantity == quantity
