"""Evidence confirmation must never become a second economic booking."""

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal

import pytest
from portfolio_common.domain.transaction.source_evidence_revision import (
    FxPnlBasisEvidence,
    FxSourceEvidenceConfirmation,
    SourceEvidenceConfirmationRejected,
    confirm_missing_fx_source,
)

ZERO = Decimal("0")


def basis(source=None, *, fx=ZERO, capital=ZERO, total=ZERO):
    return FxPnlBasisEvidence(source=source, capital=capital, fx=fx, total=total)


@pytest.mark.parametrize("signed", [Decimal("0"), Decimal("12"), Decimal("-12")])
def test_confirmation_changes_presence_not_financial_values(signed):
    original = FxSourceEvidenceConfirmation(
        local=basis(), base=basis(signed, fx=signed, total=signed)
    )
    confirmed = confirm_missing_fx_source(original, local=ZERO, base=signed)
    assert original.local.source is None
    assert confirmed.local.source == ZERO
    assert confirmed.base == original.base
    assert (confirmed.local.capital, confirmed.local.fx, confirmed.local.total) == (
        original.local.capital,
        original.local.fx,
        original.local.total,
    )
    assert confirmed.confirmed_bases == ("local",)
    with pytest.raises(FrozenInstanceError):
        confirmed.local = basis(Decimal("99"))


def test_both_missing_are_confirmed_without_truthiness_defaults():
    original = FxSourceEvidenceConfirmation(local=basis(), base=basis())
    confirmed = confirm_missing_fx_source(original, local=ZERO, base=ZERO)
    assert confirmed.confirmed_bases == ("local", "base")
    assert original.local.source is original.base.source is None


@pytest.mark.parametrize("amount", [Decimal("1"), Decimal("-1")])
def test_nonzero_confirmation_is_not_evidence_only(amount):
    original = FxSourceEvidenceConfirmation(local=basis(), base=basis())
    with pytest.raises(SourceEvidenceConfirmationRejected, match="NON_ZERO"):
        confirm_missing_fx_source(original, local=amount, base=ZERO)


def test_supplied_source_cannot_be_replaced_even_if_output_would_normalize_equal():
    original = FxSourceEvidenceConfirmation(
        local=basis(), base=basis(Decimal("12"), fx=Decimal("12"), total=Decimal("12"))
    )
    with pytest.raises(SourceEvidenceConfirmationRejected, match="SOURCE_CHANGED"):
        confirm_missing_fx_source(original, local=ZERO, base=ZERO)


def test_already_complete_source_does_not_mint_another_revision():
    original = FxSourceEvidenceConfirmation(local=basis(ZERO), base=basis(ZERO))
    with pytest.raises(SourceEvidenceConfirmationRejected, match="NO_MISSING"):
        confirm_missing_fx_source(original, local=ZERO, base=ZERO)


@pytest.mark.parametrize(
    "changed",
    [
        basis(capital=Decimal("1")),
        basis(fx=Decimal("1"), total=Decimal("1")),
        basis(total=Decimal("1")),
    ],
)
def test_confirmation_refuses_to_change_or_reinterpret_economics(changed):
    original = FxSourceEvidenceConfirmation(local=changed, base=basis())
    with pytest.raises(SourceEvidenceConfirmationRejected, match="ECONOMICS"):
        confirm_missing_fx_source(original, local=ZERO, base=ZERO)


@pytest.mark.parametrize("invalid", [False, 0, 0.0, "0", Decimal("NaN"), Decimal("Infinity")])
def test_invalid_financial_inputs_are_not_coerced_to_zero(invalid):
    with pytest.raises((TypeError, ValueError)):
        FxPnlBasisEvidence(source=invalid, capital=ZERO, fx=ZERO, total=ZERO)


def test_missing_confirmation_basis_is_refused():
    original = FxSourceEvidenceConfirmation(local=basis(), base=basis())
    with pytest.raises(SourceEvidenceConfirmationRejected, match="CONFIRMATION_REQUIRED"):
        confirm_missing_fx_source(original, local=None, base=ZERO)


def test_known_source_must_agree_with_retained_complete_output():
    original = FxSourceEvidenceConfirmation(local=basis(), base=basis(ZERO))
    original = replace(original, base=replace(original.base, fx=Decimal("12")))
    with pytest.raises(SourceEvidenceConfirmationRejected, match="ECONOMICS"):
        confirm_missing_fx_source(original, local=ZERO, base=ZERO)
