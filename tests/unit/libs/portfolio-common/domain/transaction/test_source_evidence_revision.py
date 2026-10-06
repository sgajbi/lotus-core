"""Evidence confirmation must never become a second economic booking."""

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext

import pytest
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.financial.precision import DecimalPrecisionError
from portfolio_common.domain.transaction.source_evidence_revision import (
    FxPnlBasisEvidence,
    FxSourceEvidenceConfirmation,
    SourceEvidenceConfirmationRejected,
    canonical_transaction_numeric_material,
    confirm_missing_fx_source,
    source_confirmation_material,
)

ZERO = Decimal("0")


@pytest.mark.parametrize(
    "left,right",
    [
        ("0", "0E-10"),
        ("-0", "0.0000000000"),
        ("12", "12.0000000000"),
        ("-12", "-12.0000000000"),
        ("1E-10", "0.0000000001000"),
        ("99999999.9999999999", "99999999.999999999900000000000000000000"),
    ],
)
def test_source_cut_decimal_representation_is_lossless_under_low_ambient_precision(left, right):
    with localcontext() as context:
        context.prec = 3
        original = {"amount": Decimal(left), "missing": None, "scope": "unchanged"}
        projected = canonical_transaction_numeric_material(original)
        equivalent = canonical_transaction_numeric_material(original | {"amount": Decimal(right)})
        assert canonical_content_hash(projected) == canonical_content_hash(equivalent)
        assert projected["amount"] == Decimal(left)
        assert projected.keys() == original.keys()
        assert projected["missing"] is None and projected["scope"] == "unchanged"
        assert str(original["amount"]) == left


@pytest.mark.parametrize(
    "value", ["1E-11", "100000000", "12345678901234567890123456789.1", "NaN", "Infinity"]
)
def test_source_cut_rejects_unpersistable_values_instead_of_rounding(value):
    with localcontext() as context:
        context.prec = 3
        with pytest.raises(DecimalPrecisionError):
            canonical_transaction_numeric_material({"amount": Decimal(value)})


def test_source_cut_preserves_smallest_quantum_and_null_zero_distinction():
    hashes = {
        canonical_content_hash(canonical_transaction_numeric_material({"amount": value}))
        for value in (None, Decimal("0"), Decimal("1E-10"), Decimal("-1E-10"))
    }
    assert len(hashes) == 4


@pytest.mark.parametrize("value", ["-0", "0", "12", "-12", "0.0000000001"])
def test_new_confirmation_material_preserves_values_and_unsigned_zero_before_hash(value):
    source = {"local": Decimal(value), "base": Decimal("0")}
    source_tuple = source["local"].as_tuple()
    original = {"receipt": "untouched", "amount": Decimal("-0")}
    with localcontext() as context:
        context.prec = 3
        _, values, receipt = source_confirmation_material(
            raw_id="7",
            raw_sha256="a" * 64,
            original_receipt=original,
            request_sha256="b" * 64,
            original_output=original,
            confirmed_source=source,
            original_presence={"local": False, "base": True},
        )
    assert values.keys() == source.keys() and values["local"] == Decimal(value)
    assert values["local"].as_tuple().exponent == -10
    assert not values["base"].is_signed()
    if values["local"].is_zero():
        assert not values["local"].is_signed()
    assert source["local"].as_tuple() == source_tuple and str(original["amount"]) == "-0"
    assert receipt["algorithm_id"] == "fx-source-evidence-confirmation"


def test_new_confirmation_material_rejects_excess_precision_before_rounding():
    with pytest.raises(DecimalPrecisionError):
        source_confirmation_material(
            raw_id="7",
            raw_sha256="a" * 64,
            original_receipt={},
            request_sha256="b" * 64,
            original_output={},
            confirmed_source={"local": Decimal("1E-11"), "base": ZERO},
            original_presence={"local": False, "base": True},
        )


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
