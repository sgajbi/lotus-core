"""Verify framework-neutral preparation of transactions for cost processing."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from portfolio_common.domain.cost_basis_method import CostBasisMethod

from src.services.portfolio_transaction_processing_service.app.application import (
    cost_basis_processing,
)
from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction


def _transaction(transaction_type: str = "BUY") -> BookedTransaction:
    return BookedTransaction(
        transaction_id="TX-COST-PREP-001",
        portfolio_id="PB-SG-001",
        instrument_id="INST-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 4, 10, 9, 30, tzinfo=timezone.utc),
        transaction_type=transaction_type,
        quantity=Decimal("10"),
        price=Decimal("25.50"),
        gross_transaction_amount=Decimal("255.00"),
        trade_currency="SGD",
        currency="SGD",
    )


def test_prepare_cost_transaction_applies_booking_policy() -> None:
    prepared = cost_basis_processing.prepare_cost_transaction(
        _transaction(),
        cost_basis_method="fifo",
        instrument_reference_available=True,
    )

    assert prepared.transaction_type == "BUY"
    assert prepared.cost_basis_method is CostBasisMethod.FIFO
    assert prepared.route is cost_basis_processing.CostProcessingRoute.COST_BASIS
    assert prepared.transaction.economic_event_id == "EVT-BUY-PB-SG-001-TX-COST-PREP-001"
    assert prepared.transaction.linked_transaction_group_id == (
        "LTG-BUY-PB-SG-001-TX-COST-PREP-001"
    )
    assert prepared.transaction.calculation_policy_id == "BUY_DEFAULT_POLICY"
    assert prepared.transaction.calculation_policy_version == "1.0.0"


def test_prepare_cost_transaction_classifies_fx_without_instrument_reference() -> None:
    prepared = cost_basis_processing.prepare_cost_transaction(
        replace(
            _transaction("fx_forward"),
            component_type="FX_CONTRACT_OPEN",
            instrument_id="",
            security_id="",
        ),
        cost_basis_method=CostBasisMethod.AVCO,
        instrument_reference_available=False,
    )

    assert prepared.transaction_type == "FX_FORWARD"
    assert prepared.cost_basis_method is CostBasisMethod.AVCO
    assert prepared.route is cost_basis_processing.CostProcessingRoute.FOREIGN_EXCHANGE
    assert prepared.transaction.fx_contract_id is not None
    assert prepared.transaction.instrument_id == prepared.transaction.fx_contract_id
    assert prepared.transaction.security_id == prepared.transaction.fx_contract_id


def test_prepare_cost_transaction_rejects_missing_product_reference() -> None:
    with pytest.raises(cost_basis_processing.InstrumentReferenceUnavailableError) as raised:
        cost_basis_processing.prepare_cost_transaction(
            _transaction(),
            cost_basis_method=CostBasisMethod.FIFO,
            instrument_reference_available=False,
        )

    assert raised.value.portfolio_id == "PB-SG-001"
    assert raised.value.transaction_id == "TX-COST-PREP-001"
    assert raised.value.security_id == "SEC-001"


def test_prepare_cost_transaction_allows_portfolio_adjustment_without_reference() -> None:
    prepared = cost_basis_processing.prepare_cost_transaction(
        replace(_transaction(" adjustment "), instrument_id="", security_id=""),
        cost_basis_method=CostBasisMethod.FIFO,
        instrument_reference_available=False,
    )

    assert prepared.transaction_type == "ADJUSTMENT"
    assert prepared.route is cost_basis_processing.CostProcessingRoute.COST_BASIS
