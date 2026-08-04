"""Verify linked redemption groups cannot double-count accrued interest."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BookedTransaction,
)
from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    redemption as redemption_domain,
)

RedemptionLinkedEventValidationError = redemption_domain.RedemptionLinkedEventValidationError
RedemptionLinkedEventValidationReasonCode = (
    redemption_domain.RedemptionLinkedEventValidationReasonCode
)
assert_linked_redemption_interest_unambiguous = (
    redemption_domain.assert_linked_redemption_interest_unambiguous
)
requires_linked_redemption_interest_history = (
    redemption_domain.requires_linked_redemption_interest_history
)


def _transaction(
    transaction_id: str,
    transaction_type: str,
    **changes: object,
) -> BookedTransaction:
    values: dict[str, object] = {
        "transaction_id": transaction_id,
        "portfolio_id": "PORT-REDEMPTION-01",
        "instrument_id": "BOND-01",
        "security_id": "BOND-01",
        "transaction_date": datetime(2026, 7, 15, tzinfo=UTC),
        "transaction_type": transaction_type,
        "quantity": Decimal("100"),
        "price": Decimal("100"),
        "gross_transaction_amount": Decimal("10000"),
        "trade_currency": "USD",
        "currency": "USD",
        "linked_transaction_group_id": " GROUP-REDEMPTION-01 ",
    }
    values.update(changes)
    return BookedTransaction(**values)  # type: ignore[arg-type]


def _redemption(**changes: object) -> BookedTransaction:
    changes.setdefault("accrued_interest_proceeds_local", Decimal("25"))
    changes.setdefault("external_cash_transaction_id", "REDEMPTION-01-CASHLEG")
    return _transaction(
        "REDEMPTION-01",
        "MATURITY_REDEMPTION",
        **changes,
    )


def _interest(transaction_id: str = "INTEREST-01", **changes: object) -> BookedTransaction:
    return _transaction(
        transaction_id,
        "INTEREST",
        quantity=Decimal(0),
        price=Decimal(0),
        gross_transaction_amount=Decimal("25"),
        **changes,
    )


@pytest.mark.parametrize("incoming_is_redemption", [True, False])
def test_independent_interest_and_redemption_accrual_fail_for_either_arrival_order(
    incoming_is_redemption: bool,
) -> None:
    redemption = _redemption()
    interest = _interest()
    incoming, history = (
        (redemption, [interest]) if incoming_is_redemption else (interest, [redemption])
    )

    with pytest.raises(RedemptionLinkedEventValidationError) as raised:
        assert_linked_redemption_interest_unambiguous(
            incoming=incoming,
            history=history,
        )

    assert raised.value.reason_code is (
        RedemptionLinkedEventValidationReasonCode.DUPLICATE_ACCRUED_INTEREST
    )
    assert raised.value.linked_transaction_group_id == "GROUP-REDEMPTION-01"
    assert raised.value.redemption_transaction_ids == ("REDEMPTION-01",)
    assert raised.value.interest_transaction_ids == ("INTEREST-01",)
    assert str(raised.value).startswith("REDEMPTION_017_DUPLICATE_LINKED_INTEREST")


def test_generated_redemption_interest_component_is_not_duplicate_income() -> None:
    redemption = _redemption()
    generated_interest = redemption_domain.build_redemption_accrued_interest_component(redemption)

    assert generated_interest is not None
    assert redemption_domain.is_generated_redemption_accrued_interest(generated_interest)
    assert_linked_redemption_interest_unambiguous(
        incoming=redemption,
        history=[generated_interest],
    )


def test_independent_interest_is_still_rejected_beside_generated_component() -> None:
    redemption = _redemption()
    generated_interest = redemption_domain.build_redemption_accrued_interest_component(redemption)

    assert generated_interest is not None
    with pytest.raises(RedemptionLinkedEventValidationError) as raised:
        assert_linked_redemption_interest_unambiguous(
            incoming=_interest("INTEREST-INDEPENDENT"),
            history=[redemption, generated_interest],
        )

    assert raised.value.interest_transaction_ids == ("INTEREST-INDEPENDENT",)


def test_caller_cannot_masquerade_as_a_generated_interest_component() -> None:
    redemption = _redemption()
    forged = _interest(
        "FORGED-INTEREST",
        component_type=redemption_domain.REDEMPTION_ACCRUED_INTEREST_COMPONENT,
        component_id="FORGED-INTEREST:v1",
        originating_transaction_id=redemption.transaction_id,
        originating_transaction_type=redemption.transaction_type,
    )

    assert not redemption_domain.is_generated_redemption_accrued_interest(forged)
    with pytest.raises(RedemptionLinkedEventValidationError):
        assert_linked_redemption_interest_unambiguous(
            incoming=redemption,
            history=[forged],
        )


@pytest.mark.parametrize(
    "history",
    [
        [_interest(linked_transaction_group_id="GROUP-OTHER")],
        [_transaction("DIVIDEND-01", "DIVIDEND")],
        [_transaction("CASH-01", "ADJUSTMENT")],
    ],
)
def test_unrelated_linked_income_and_cash_patterns_do_not_trigger(
    history: list[BookedTransaction],
) -> None:
    assert_linked_redemption_interest_unambiguous(
        incoming=_redemption(),
        history=history,
    )


def test_history_read_is_required_only_for_a_leg_that_can_complete_ambiguity() -> None:
    assert requires_linked_redemption_interest_history(_redemption())
    assert requires_linked_redemption_interest_history(_interest())
    assert not requires_linked_redemption_interest_history(
        _redemption(accrued_interest_proceeds_local=Decimal(0))
    )
    assert not requires_linked_redemption_interest_history(
        replace(_interest(), linked_transaction_group_id=None)
    )


def test_validation_is_a_noop_without_group_or_source_redemption() -> None:
    assert_linked_redemption_interest_unambiguous(
        incoming=replace(_interest(), linked_transaction_group_id=None),
        history=[_redemption()],
    )
    generated = redemption_domain.build_redemption_accrued_interest_component(_redemption())
    assert generated is not None
    assert_linked_redemption_interest_unambiguous(incoming=generated, history=[])
