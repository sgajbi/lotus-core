from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.services.portfolio_transaction_processing_service.app.domain import (
    BookedTransaction,
    build_transaction_correction_identity,
    build_transaction_semantic_identity,
)


def _transaction() -> BookedTransaction:
    return BookedTransaction(
        transaction_id="TX-SEMANTIC-001",
        portfolio_id="PB-001",
        instrument_id="INST-001",
        security_id="SEC-001",
        transaction_date=datetime(2026, 4, 10, 9, 30, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity=Decimal("10.00"),
        price=Decimal("25.500"),
        gross_transaction_amount=Decimal("255.000"),
        trade_currency="SGD",
        currency="SGD",
        calculation_policy_id="BUY_DEFAULT",
        calculation_policy_version="1.0.0",
        created_at=datetime(2026, 4, 10, 9, 31, tzinfo=timezone.utc),
        epoch=3,
    )


def test_semantic_identity_is_stable_across_non_material_representations() -> None:
    transaction = _transaction()
    equivalent = replace(
        transaction,
        transaction_date=datetime(
            2026,
            4,
            10,
            17,
            30,
            tzinfo=timezone(timedelta(hours=8)),
        ),
        quantity=Decimal("10"),
        price=Decimal("25.5"),
        gross_transaction_amount=Decimal("255"),
        created_at=datetime(2026, 4, 11, 12, 0, tzinfo=timezone.utc),
    )

    identity = build_transaction_semantic_identity(transaction)

    assert identity == build_transaction_semantic_identity(equivalent)
    assert identity.semantic_key == "transaction-processing:v1:PB-001:TX-SEMANTIC-001:3"
    assert identity.payload_fingerprint.startswith("sha256:")
    assert len(identity.payload_fingerprint) == 71


def test_semantic_identity_detects_material_payload_change() -> None:
    transaction = _transaction()

    changed_amount = build_transaction_semantic_identity(
        replace(transaction, gross_transaction_amount=Decimal("256"))
    )
    changed_policy = build_transaction_semantic_identity(
        replace(transaction, calculation_policy_version="2.0.0")
    )
    original = build_transaction_semantic_identity(transaction)

    assert changed_amount.semantic_key == original.semantic_key
    assert changed_amount.payload_fingerprint != original.payload_fingerprint
    assert changed_policy.semantic_key == original.semantic_key
    assert changed_policy.payload_fingerprint != original.payload_fingerprint


def test_semantic_identity_ignores_processor_owned_outputs_added_before_replay() -> None:
    transaction = replace(
        _transaction(),
        calculation_policy_id=None,
        calculation_policy_version=None,
    )
    enriched_after_processing = replace(
        transaction,
        allocated_cost_basis_base=Decimal("254"),
        allocated_cost_basis_local=Decimal("254"),
        gross_cost=Decimal("255"),
        net_cost=Decimal("254"),
        net_cost_local=Decimal("254"),
        realized_capital_pnl_base=Decimal("1"),
        realized_capital_pnl_local=Decimal("1"),
        realized_fx_pnl_base=Decimal("0"),
        realized_fx_pnl_local=Decimal("0"),
        realized_gain_loss=Decimal("1"),
        realized_gain_loss_local=Decimal("1"),
        realized_total_pnl_base=Decimal("1"),
        realized_total_pnl_local=Decimal("1"),
        transaction_fx_rate=Decimal("1"),
        economic_event_id="EVT-BUY-PB-001-TX-SEMANTIC-001",
        linked_transaction_group_id="LTG-BUY-PB-001-TX-SEMANTIC-001",
        calculation_policy_id="BUY_DEFAULT_POLICY",
        calculation_policy_version="1.0.0",
    )

    assert build_transaction_semantic_identity(
        enriched_after_processing
    ) == build_transaction_semantic_identity(transaction)


def test_semantic_identity_keeps_custom_linkage_and_policy_material() -> None:
    transaction = _transaction()
    original = build_transaction_semantic_identity(transaction)

    for changed_transaction in (
        replace(transaction, economic_event_id="CLIENT-EVENT-001"),
        replace(transaction, linked_transaction_group_id="CLIENT-GROUP-001"),
        replace(transaction, calculation_policy_id="CLIENT_POLICY"),
        replace(transaction, calculation_policy_version="2.0.0"),
    ):
        changed = build_transaction_semantic_identity(changed_transaction)
        assert changed.semantic_key == original.semantic_key
        assert changed.payload_fingerprint != original.payload_fingerprint


def test_semantic_identity_normalizes_only_auto_generated_cash_leg_identity() -> None:
    transaction = replace(
        _transaction(),
        cash_entry_mode="AUTO_GENERATE",
        external_cash_transaction_id=None,
    )
    generated_cash_leg_link = replace(
        transaction,
        external_cash_transaction_id="TX-SEMANTIC-001-CASHLEG",
    )
    caller_supplied_cash_leg_link = replace(
        transaction,
        external_cash_transaction_id="CLIENT-CASH-LEG-001",
    )
    upstream_supplied_generated_shape = replace(
        transaction,
        cash_entry_mode="UPSTREAM_PROVIDED",
        external_cash_transaction_id="TX-SEMANTIC-001-CASHLEG",
    )

    original = build_transaction_semantic_identity(transaction)

    assert build_transaction_semantic_identity(generated_cash_leg_link) == original
    assert (
        build_transaction_semantic_identity(caller_supplied_cash_leg_link).payload_fingerprint
        != original.payload_fingerprint
    )
    assert (
        build_transaction_semantic_identity(upstream_supplied_generated_shape).payload_fingerprint
        != original.payload_fingerprint
    )


def test_semantic_identity_separates_processing_epochs() -> None:
    transaction = _transaction()

    next_epoch = build_transaction_semantic_identity(replace(transaction, epoch=4))
    original = build_transaction_semantic_identity(transaction)

    assert next_epoch.semantic_key != original.semantic_key


def test_correction_identity_is_payload_specific_and_preserves_base_fingerprint() -> None:
    transaction = _transaction()
    corrected = replace(
        transaction, quantity=Decimal("12"), gross_transaction_amount=Decimal("306")
    )

    original_correction = build_transaction_correction_identity(transaction)
    corrected_correction = build_transaction_correction_identity(corrected)

    assert (
        original_correction.payload_fingerprint
        == build_transaction_semantic_identity(transaction).payload_fingerprint
    )
    assert (
        corrected_correction.payload_fingerprint
        == build_transaction_semantic_identity(corrected).payload_fingerprint
    )
    assert original_correction.semantic_key != corrected_correction.semantic_key
    assert corrected_correction.semantic_key.startswith(
        "transaction-correction:v1:PB-001:TX-SEMANTIC-001:3:sha256:"
    )
