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
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    CashAccountRequiredValidationError,
    CashAccountRequiredValidationReasonCode,
)


def _transaction(transaction_type: str = "BUY") -> BookedTransaction:
    return BookedTransaction(
        transaction_id="TX-COST-PREP-001",
        portfolio_id="PB-SG-001",
        instrument_id="INST-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 4, 10, 9, 30, tzinfo=timezone.utc),
        settlement_date=datetime(2026, 4, 12, 9, 30, tzinfo=timezone.utc),
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


@pytest.mark.parametrize("transaction_type", ["DEPOSIT", "WITHDRAWAL", "FEE", "TAX"])
def test_prepare_cash_account_booking_requires_authoritative_cash_metadata(
    transaction_type: str,
) -> None:
    with pytest.raises(CashAccountRequiredValidationError) as raised:
        cost_basis_processing.prepare_cost_transaction(
            _transaction(transaction_type),
            cost_basis_method=CostBasisMethod.FIFO,
            instrument_reference_available=True,
            instrument_product_type="EQUITY",
            instrument_asset_class="EQUITY",
        )

    assert raised.value.reason_code is CashAccountRequiredValidationReasonCode.NON_CASH_INSTRUMENT


def test_prepare_cash_account_booking_accepts_authoritative_cash_metadata() -> None:
    prepared = cost_basis_processing.prepare_cost_transaction(
        _transaction("FEE"),
        cost_basis_method=CostBasisMethod.FIFO,
        instrument_reference_available=True,
        instrument_product_type="Cash",
        instrument_asset_class="Cash",
    )

    assert prepared.transaction_type == "FEE"


_REDEMPTION_TYPES = (
    "MATURITY_REDEMPTION",
    "CALL_REDEMPTION",
    "PARTIAL_REDEMPTION",
)


@pytest.mark.parametrize("transaction_type", _REDEMPTION_TYPES)
def test_prepare_redemption_requires_source_owned_settlement_date(
    transaction_type: str,
) -> None:
    with pytest.raises(ValueError, match="settlement_date is required"):
        cost_basis_processing.prepare_cost_transaction(
            replace(
                _transaction(transaction_type),
                settlement_date=None,
                cash_entry_mode="UPSTREAM_PROVIDED",
            ),
            cost_basis_method=CostBasisMethod.FIFO,
            instrument_reference_available=True,
        )


@pytest.mark.parametrize("transaction_type", _REDEMPTION_TYPES)
def test_prepare_redemption_rejects_omitted_cash_mode_without_account(
    transaction_type: str,
) -> None:
    with pytest.raises(ValueError, match="settlement_cash_account_id is required"):
        cost_basis_processing.prepare_cost_transaction(
            _transaction(transaction_type),
            cost_basis_method=CostBasisMethod.FIFO,
            instrument_reference_available=True,
        )


@pytest.mark.parametrize("transaction_type", _REDEMPTION_TYPES)
def test_prepare_redemption_rejects_auto_generate_without_account(
    transaction_type: str,
) -> None:
    with pytest.raises(ValueError, match="settlement_cash_account_id is required"):
        cost_basis_processing.prepare_cost_transaction(
            replace(_transaction(transaction_type), cash_entry_mode="AUTO_GENERATE"),
            cost_basis_method=CostBasisMethod.FIFO,
            instrument_reference_available=True,
        )


@pytest.mark.parametrize("transaction_type", _REDEMPTION_TYPES)
@pytest.mark.parametrize(
    ("cash_entry_mode", "settlement_cash_account_id", "expected_mode"),
    [
        (None, "CASH-SGD-001", "AUTO_GENERATE"),
        ("AUTO_GENERATE", "CASH-SGD-001", "AUTO_GENERATE"),
        ("UPSTREAM_PROVIDED", None, "UPSTREAM_PROVIDED"),
    ],
)
def test_prepare_redemption_accepts_supported_cash_leg_contracts(
    transaction_type: str,
    cash_entry_mode: str | None,
    settlement_cash_account_id: str | None,
    expected_mode: str,
) -> None:
    prepared = cost_basis_processing.prepare_cost_transaction(
        replace(
            _transaction(transaction_type),
            cash_entry_mode=cash_entry_mode,
            settlement_cash_account_id=settlement_cash_account_id,
        ),
        cost_basis_method=CostBasisMethod.FIFO,
        instrument_reference_available=True,
    )

    assert prepared.transaction.cash_entry_mode == expected_mode


@pytest.mark.parametrize("transaction_type", _REDEMPTION_TYPES)
def test_prepare_zero_cash_redemption_allows_omitted_generated_leg_metadata(
    transaction_type: str,
) -> None:
    prepared = cost_basis_processing.prepare_cost_transaction(
        replace(
            _transaction(transaction_type),
            price=Decimal(0),
            gross_transaction_amount=Decimal(0),
            principal_proceeds_local=Decimal(0),
            accrued_interest_proceeds_local=Decimal(0),
            embedded_fee_amount_local=Decimal(0),
            embedded_tax_amount_local=Decimal(0),
            trade_fee=Decimal(0),
        ),
        cost_basis_method=CostBasisMethod.FIFO,
        instrument_reference_available=True,
    )

    assert prepared.transaction.cash_entry_mode == "AUTO_GENERATE"
    assert prepared.transaction.settlement_cash_account_id is None
