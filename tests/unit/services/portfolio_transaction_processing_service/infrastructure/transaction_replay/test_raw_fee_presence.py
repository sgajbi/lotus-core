"""Exact raw authority bounds history preparation without changing financial truth."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from portfolio_common.domain.transaction import transaction_payload_fingerprint

from .test_booked_transaction import _fee_source_fixture, fee_authority


@pytest.mark.parametrize("rows", [1, 72, 640])
def test_raw_history_bounds_hash_work_and_preserves_projection(monkeypatch, rows):
    original, canonical, costs, raw = _fee_source_fixture("none")
    fingerprint = MagicMock(wraps=transaction_payload_fingerprint)
    monkeypatch.setattr(fee_authority, "transaction_payload_fingerprint", fingerprint)
    expected = dict.fromkeys(fee_authority.TRANSACTION_FEE_COMPONENT_FIELDS) | {
        "trade_fee": original.trade_fee
    }

    for _ in range(rows):
        projection = fee_authority.qualify_transaction_fee_source(
            canonical, costs, [raw], derived_financial=True
        )
        assert projection == expected

    assert fingerprint.call_count == 3 * rows


@pytest.mark.parametrize("derived", [False, True])
@pytest.mark.parametrize(
    "field,value",
    [
        ("gross_transaction_amount", "not-numeric"),
        ("quantity", "not-numeric"),
        ("currency", ""),
        ("tenant_id", ""),
        ("payload_fingerprint", "foreign"),
    ],
)
def test_valid_raw_never_hides_invalid_canonical_input(field, value, derived):
    _, canonical, costs, raw = _fee_source_fixture("none")
    with pytest.raises(ValueError):
        fee_authority.qualify_transaction_fee_source(
            canonical | {field: value}, costs, [raw], derived_financial=derived
        )


@pytest.mark.parametrize("derived", [False, True])
def test_positive_ledger_disagreement_is_not_hidden_by_exact_raw(derived):
    _, canonical, costs, raw = _fee_source_fixture("sparse")
    costs[0]["amount"] = Decimal("2")
    with pytest.raises(ValueError, match="conflict"):
        fee_authority.qualify_transaction_fee_source(
            canonical, costs, [raw], derived_financial=derived
        )
