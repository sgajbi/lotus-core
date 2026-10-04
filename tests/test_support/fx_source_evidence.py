"""Execute the shipped FX producer to seed independent reader evidence controls."""

from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from portfolio_common.database_models import Transaction
from portfolio_common.domain.tenant import TenantId
from portfolio_common.domain.transaction.payload_identity import transaction_payload_fingerprint
from portfolio_common.event_mapping import transaction_event_v1_payload
from portfolio_common.events import TransactionEvent

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction.fx import (
    build_fx_processed_transaction,
)

TENANT = TenantId("QCP_FX_SOURCE_TEST")


def fx_source_fixture(
    local: Decimal | None, base: Decimal | None, *, mode: str = "UPSTREAM_PROVIDED"
) -> tuple[dict[str, Any], BookedTransaction, Transaction]:
    source = BookedTransaction(
        transaction_id="QCP-FX-HISTORY",
        portfolio_id="QCP-FX-PORT",
        instrument_id="FXC-EURUSD",
        security_id="FXC-EURUSD",
        transaction_date=datetime(2026, 4, 1, 9, tzinfo=UTC),
        created_at=datetime(2026, 4, 1, 9, tzinfo=UTC),
        transaction_type="FX_FORWARD",
        component_type="FX_CONTRACT_CLOSE",
        quantity=Decimal("0"),
        price=Decimal("0"),
        gross_transaction_amount=Decimal("0"),
        trade_currency="USD",
        currency="USD",
        pair_base_currency="EUR",
        pair_quote_currency="USD",
        buy_currency="USD",
        sell_currency="EUR",
        buy_amount=Decimal("1095000"),
        sell_amount=Decimal("1000000"),
        contract_rate=Decimal("1.095"),
        fx_rate_quote_convention="QUOTE_PER_BASE",
        fx_contract_id="QCP-FX-CONTRACT",
        tenant_id=TENANT.value,
        fx_realized_pnl_mode=mode,
        realized_fx_pnl_local=local,
        realized_fx_pnl_base=base,
        realized_capital_pnl_local=Decimal("100"),
        realized_capital_pnl_base=Decimal("100"),
    )
    event = TransactionEvent.model_validate(
        {
            name: value
            for name, value in asdict(source).items()
            if name in TransactionEvent.model_fields
        }
    )
    raw = transaction_event_v1_payload(event)
    processed = build_fx_processed_transaction(source)
    ledger = Transaction(
        **{
            name: value
            for name, value in asdict(processed).items()
            if name in Transaction.__table__.columns and name != "calculation_lineage"
        }
    )
    assert processed.calculation_lineage is not None
    ledger.calculation_lineage = processed.calculation_lineage.lineage_payload()
    ledger.payload_fingerprint = transaction_payload_fingerprint(raw)
    return raw, processed, ledger
