"""Verify deterministic selection of the affected cost-basis persistence suffix."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.application.cost_basis_processing.persistence_scope import (  # noqa: E501
    CostBasisTransactionPersistenceScope,
    affected_transaction_suffix,
    build_cost_basis_persistence_plan,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostBasisTransaction,
)


def _transaction(transaction_id: str, day: int) -> CostBasisTransaction:
    return CostBasisTransaction(
        transaction_id=transaction_id,
        portfolio_id="PORT-SCOPE-01",
        instrument_id="INSTRUMENT-SCOPE-01",
        security_id="SECURITY-SCOPE-01",
        transaction_date=datetime(2026, 7, day, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity=Decimal("1"),
        price=Decimal("10"),
        gross_transaction_amount=Decimal("10"),
        trade_currency="SGD",
        currency="SGD",
        portfolio_base_currency="SGD",
        transaction_fx_rate=Decimal("1"),
    )


def test_affected_transaction_suffix_includes_every_later_calculation() -> None:
    earlier = _transaction("BUY-EARLIER", 1)
    incoming = _transaction("BUY-BACKDATED", 2)
    later = _transaction("SELL-LATER", 3)

    affected = affected_transaction_suffix(
        processed=[earlier, incoming, later],
        incoming_transaction_ids={incoming.transaction_id},
    )

    assert affected == (incoming, later)


def test_affected_transaction_suffix_fails_closed_when_incoming_is_absent() -> None:
    with pytest.raises(
        ValueError,
        match="Processed transaction timeline omitted the incoming transaction",
    ):
        affected_transaction_suffix(
            processed=[_transaction("BUY-EXISTING", 1)],
            incoming_transaction_ids={"BUY-MISSING"},
        )


def test_complete_timeline_scope_includes_calculated_prefix_authority() -> None:
    earlier = _transaction("BUY-EARLIER", 1)
    incoming = _transaction("BUY-BACKDATED", 2)
    later = _transaction("SELL-LATER", 3)

    plan = build_cost_basis_persistence_plan(
        processed=[earlier, incoming, later],
        incoming_transaction_ids={incoming.transaction_id},
        scope=CostBasisTransactionPersistenceScope.COMPLETE_TIMELINE,
    )

    assert plan.economics_transactions == (earlier, incoming, later)
    assert plan.child_state_transactions == (incoming, later)


def test_affected_suffix_scope_preserves_incremental_write_boundary() -> None:
    earlier = _transaction("BUY-EARLIER", 1)
    incoming = _transaction("BUY-BACKDATED", 2)
    later = _transaction("SELL-LATER", 3)

    plan = build_cost_basis_persistence_plan(
        processed=[earlier, incoming, later],
        incoming_transaction_ids={incoming.transaction_id},
        scope=CostBasisTransactionPersistenceScope.AFFECTED_SUFFIX,
    )

    assert plan.economics_transactions == (incoming, later)
    assert plan.child_state_transactions == (incoming, later)
