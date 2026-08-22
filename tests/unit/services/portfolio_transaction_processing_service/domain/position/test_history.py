"""Test deterministic position-history domain construction."""

from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path

import pytest
from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
)

from src.services.portfolio_transaction_processing_service.app.domain import BookedTransaction
from src.services.portfolio_transaction_processing_service.app.domain.position.history import (
    PositionHistoryInvariantError,
    PositionHistoryRecord,
    PositionRecalculationState,
    build_position_history,
    order_position_transactions,
    position_transaction_ordering_key,
)

REPO_ROOT = Path(__file__).resolve().parents[6]
SERVICE_TEST_ROOT = REPO_ROOT / "tests/unit/services/portfolio_transaction_processing_service"
TARGET_TEST = SERVICE_TEST_ROOT / "domain/position/test_history.py"
RETIRED_TEST = SERVICE_TEST_ROOT / "position/test_position_history_domain.py"


def test_position_history_tests_are_owned_by_domain_boundary() -> None:
    assert Path(__file__).resolve() == TARGET_TEST.resolve()
    assert not RETIRED_TEST.exists()
    assert list((SERVICE_TEST_ROOT / "position").glob("*.py")) == []


def _transaction(
    transaction_id: str,
    transaction_type: str,
    *,
    transaction_date: datetime | None = None,
    quantity: Decimal = Decimal("0"),
    net_cost: Decimal | None = None,
    net_cost_local: Decimal | None = None,
    child_sequence_hint: int | None = None,
    target_instrument_id: str | None = None,
    created_at: datetime | None = None,
    portfolio_id: str = "PB-001",
    security_id: str = "SEC-001",
    calculation_lineage: CalculationLineage | None = None,
) -> BookedTransaction:
    return BookedTransaction(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        instrument_id=security_id,
        security_id=security_id,
        transaction_date=transaction_date or datetime(2026, 4, 10, 9, 30, tzinfo=timezone.utc),
        transaction_type=transaction_type,
        quantity=quantity,
        price=Decimal("10"),
        gross_transaction_amount=abs(quantity * Decimal("10")),
        trade_currency="SGD",
        currency="SGD",
        net_cost=net_cost,
        net_cost_local=net_cost_local,
        child_sequence_hint=child_sequence_hint,
        target_instrument_id=target_instrument_id,
        created_at=created_at,
        calculation_lineage=calculation_lineage,
    )


def _transaction_lineage(source_revision: str) -> CalculationLineage:
    return build_calculation_lineage(
        algorithm_id="transaction-cost-basis-calculation",
        algorithm_version=1,
        intermediate_precision=28,
        input_payload={"source_revision": source_revision},
        output_payload={"net_cost": Decimal("60"), "quantity": Decimal("5")},
    )


def test_order_position_transactions_uses_canonical_dependency_and_target_order() -> None:
    transaction_time = datetime(2026, 4, 10, 9, 30, tzinfo=timezone.utc)
    transactions = (
        _transaction("CASH", "CASH_CONSIDERATION", transaction_date=transaction_time),
        _transaction(
            "TARGET-2",
            "DEMERGER_IN",
            transaction_date=transaction_time,
            child_sequence_hint=2,
            target_instrument_id="SEC-C",
        ),
        _transaction("SOURCE", "DEMERGER_OUT", transaction_date=transaction_time),
        _transaction(
            "TARGET-1B",
            "DEMERGER_IN",
            transaction_date=transaction_time,
            child_sequence_hint=1,
            target_instrument_id="SEC-B",
        ),
        _transaction(
            "TARGET-1A",
            "DEMERGER_IN",
            transaction_date=transaction_time,
            child_sequence_hint=1,
            target_instrument_id="SEC-A",
        ),
    )

    ordered = order_position_transactions(transactions)

    assert tuple(transaction.transaction_id for transaction in ordered) == (
        "SOURCE",
        "TARGET-1A",
        "TARGET-1B",
        "TARGET-2",
        "CASH",
    )


@pytest.mark.parametrize("restatement_type", ["SPLIT", "REVERSE_SPLIT", "CONSOLIDATION"])
def test_same_time_position_restatement_follows_its_source_acquisition(
    restatement_type: str,
) -> None:
    transaction_time = datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)
    acquisition = _transaction(
        "BUY-SOURCE",
        "BUY",
        transaction_date=transaction_time,
        quantity=Decimal("100"),
    )
    restatement = _transaction(
        "ACTION-RESTATE",
        restatement_type,
        transaction_date=transaction_time,
        quantity=Decimal("200"),
    )

    ordered = order_position_transactions((restatement, acquisition))

    assert tuple(transaction.transaction_id for transaction in ordered) == (
        "BUY-SOURCE",
        "ACTION-RESTATE",
    )


def test_order_position_transactions_uses_ingestion_and_identity_tiebreakers() -> None:
    transaction_time = datetime(2026, 4, 10, 9, 30, tzinfo=timezone(timedelta(hours=8)))
    transactions = (
        _transaction(
            "TX-B",
            "BUY",
            transaction_date=transaction_time,
            created_at=datetime(2026, 4, 10, 2, 0, tzinfo=timezone.utc),
        ),
        _transaction(
            "TX-C",
            "BUY",
            transaction_date=transaction_time,
            created_at=datetime(2026, 4, 10, 1, 0, tzinfo=timezone.utc),
        ),
        _transaction(
            "TX-A",
            "BUY",
            transaction_date=transaction_time,
            created_at=datetime(2026, 4, 10, 1, 0, tzinfo=timezone.utc),
        ),
    )

    ordered = order_position_transactions(transactions)

    assert tuple(transaction.transaction_id for transaction in ordered) == (
        "TX-A",
        "TX-C",
        "TX-B",
    )


@pytest.mark.parametrize(
    ("updates", "expected_field"),
    [
        ({"transaction_date": datetime(2026, 4, 10, 9, 30)}, "transaction_date"),
        ({"created_at": datetime(2026, 4, 10, 9, 31)}, "created_at"),
    ],
)
def test_position_ordering_rejects_timezone_ambiguous_lineage_inputs(
    updates: dict[str, datetime],
    expected_field: str,
) -> None:
    transaction = _transaction("TX-NAIVE", "BUY", **updates)

    with pytest.raises(
        PositionHistoryInvariantError,
        match=rf"{expected_field}.*timezone-aware",
    ):
        position_transaction_ordering_key(transaction)


def test_position_ordering_canonicalizes_equivalent_aware_instants_to_utc() -> None:
    utc_transaction = _transaction(
        "TX-CANONICAL",
        "BUY",
        transaction_date=datetime(2026, 4, 10, 1, 30, tzinfo=timezone.utc),
        created_at=datetime(2026, 4, 10, 2, 0, tzinfo=timezone.utc),
    )
    singapore_transaction = _transaction(
        "TX-CANONICAL",
        "BUY",
        transaction_date=datetime(
            2026,
            4,
            10,
            9,
            30,
            tzinfo=timezone(timedelta(hours=8)),
        ),
        created_at=datetime(
            2026,
            4,
            10,
            10,
            0,
            tzinfo=timezone(timedelta(hours=8)),
        ),
    )

    assert position_transaction_ordering_key(utc_transaction) == (
        position_transaction_ordering_key(singapore_transaction)
    )


def test_position_history_uses_canonical_date_for_equivalent_cross_midnight_instants() -> None:
    utc_transaction = _transaction(
        "TX-CROSS-MIDNIGHT",
        "BUY",
        transaction_date=datetime(2026, 4, 9, 16, 30, tzinfo=timezone.utc),
        quantity=Decimal("5"),
        net_cost=Decimal("60"),
    )
    singapore_transaction = _transaction(
        "TX-CROSS-MIDNIGHT",
        "BUY",
        transaction_date=datetime(
            2026,
            4,
            10,
            0,
            30,
            tzinfo=timezone(timedelta(hours=8)),
        ),
        quantity=Decimal("5"),
        net_cost=Decimal("60"),
    )

    utc_history = build_position_history(
        anchor=None,
        transactions=(utc_transaction,),
        epoch=4,
    )
    singapore_history = build_position_history(
        anchor=None,
        transactions=(singapore_transaction,),
        epoch=4,
    )

    assert utc_history == singapore_history
    assert utc_history[0].position_date == date(2026, 4, 9)


def test_build_position_history_applies_anchor_and_returns_immutable_records() -> None:
    anchor = PositionHistoryRecord(
        portfolio_id="PB-001",
        security_id="SEC-001",
        transaction_id="TX-ANCHOR",
        position_date=date(2026, 4, 9),
        quantity=Decimal("10"),
        cost_basis=Decimal("100"),
        cost_basis_local=Decimal("95"),
        epoch=3,
    )
    buy = _transaction(
        "TX-BUY",
        "BUY",
        quantity=Decimal("5"),
        net_cost=Decimal("60"),
        net_cost_local=Decimal("55"),
    )
    sell = _transaction(
        "TX-SELL",
        "SELL",
        transaction_date=datetime(2026, 4, 11, 9, 30, tzinfo=timezone.utc),
        quantity=Decimal("3"),
        net_cost=Decimal("-24"),
        net_cost_local=Decimal("-21"),
    )

    records = build_position_history(anchor=anchor, transactions=(sell, buy), epoch=4)

    assert tuple(
        (
            record.transaction_id,
            record.position_date,
            record.quantity,
            record.cost_basis,
            record.cost_basis_local,
            record.epoch,
        )
        for record in records
    ) == (
        ("TX-BUY", date(2026, 4, 10), Decimal("15"), Decimal("160"), Decimal("150"), 4),
        ("TX-SELL", date(2026, 4, 11), Decimal("12"), Decimal("136"), Decimal("129"), 4),
    )
    assert all(record.calculation_lineage is not None for record in records)
    first_lineage = records[0].calculation_lineage
    assert first_lineage is not None
    assert first_lineage.algorithm_id == "position-history-state-transition"
    assert first_lineage.numeric_output_policy is not None
    assert first_lineage.numeric_output_policy.policy_id == ("position-history-ledger-output@1.0.0")
    with pytest.raises(FrozenInstanceError):
        records[0].quantity = Decimal("999")  # type: ignore[misc]


def test_position_history_lineage_is_deterministic_and_chains_prior_output() -> None:
    transactions = (
        _transaction("TX-BUY", "BUY", quantity=Decimal("5"), net_cost=Decimal("60")),
        _transaction(
            "TX-SELL",
            "SELL",
            transaction_date=datetime(2026, 4, 11, 9, 30, tzinfo=timezone.utc),
            quantity=Decimal("2"),
            net_cost=Decimal("-24"),
        ),
    )

    first_run = build_position_history(anchor=None, transactions=transactions, epoch=4)
    second_run = build_position_history(anchor=None, transactions=reversed(transactions), epoch=4)

    assert tuple(record.calculation_lineage for record in first_run) == tuple(
        record.calculation_lineage for record in second_run
    )
    first_lineage = first_run[0].calculation_lineage
    second_lineage = first_run[1].calculation_lineage
    assert first_lineage is not None
    assert second_lineage is not None
    assert first_lineage.output_content_hash != second_lineage.output_content_hash


def test_position_history_lineage_is_independent_of_ambient_decimal_context() -> None:
    transaction = _transaction(
        "TX-BUY",
        "BUY",
        quantity=Decimal("1.2345678901"),
        net_cost=Decimal("12.3456789012"),
        net_cost_local=Decimal("9.8765432109"),
    )

    expected = build_position_history(anchor=None, transactions=(transaction,), epoch=2)
    with localcontext() as context:
        context.prec = 6
        actual = build_position_history(anchor=None, transactions=(transaction,), epoch=2)

    assert actual == expected


def test_position_history_lineage_changes_with_material_transaction_input() -> None:
    baseline = build_position_history(
        anchor=None,
        transactions=(
            _transaction("TX-BUY", "BUY", quantity=Decimal("5"), net_cost=Decimal("60")),
        ),
        epoch=4,
    )[0]
    changed = build_position_history(
        anchor=None,
        transactions=(
            _transaction("TX-BUY", "BUY", quantity=Decimal("6"), net_cost=Decimal("60")),
        ),
        epoch=4,
    )[0]

    baseline_lineage = baseline.calculation_lineage
    changed_lineage = changed.calculation_lineage
    assert baseline_lineage is not None
    assert changed_lineage is not None
    assert baseline_lineage.input_content_hash != changed_lineage.input_content_hash
    assert baseline_lineage.output_content_hash != changed_lineage.output_content_hash


def test_position_history_lineage_binds_upstream_transaction_calculation_lineage() -> None:
    baseline = build_position_history(
        anchor=None,
        transactions=(
            _transaction(
                "TX-BUY",
                "BUY",
                quantity=Decimal("5"),
                net_cost=Decimal("60"),
                calculation_lineage=_transaction_lineage("source-revision-1"),
            ),
        ),
        epoch=4,
    )[0]
    changed = build_position_history(
        anchor=None,
        transactions=(
            _transaction(
                "TX-BUY",
                "BUY",
                quantity=Decimal("5"),
                net_cost=Decimal("60"),
                calculation_lineage=_transaction_lineage("source-revision-2"),
            ),
        ),
        epoch=4,
    )[0]

    baseline_lineage = baseline.calculation_lineage
    changed_lineage = changed.calculation_lineage
    assert baseline_lineage is not None
    assert changed_lineage is not None
    assert baseline.quantity == changed.quantity
    assert baseline.cost_basis == changed.cost_basis
    assert baseline_lineage.input_content_hash != changed_lineage.input_content_hash
    assert baseline_lineage.output_content_hash != changed_lineage.output_content_hash


def test_build_position_history_rejects_mixed_position_keys() -> None:
    transactions = (
        _transaction("TX-001", "BUY", quantity=Decimal("1")),
        _transaction(
            "TX-002",
            "BUY",
            quantity=Decimal("1"),
            security_id="SEC-OTHER",
        ),
    )

    with pytest.raises(PositionHistoryInvariantError, match="one portfolio-security key"):
        build_position_history(anchor=None, transactions=transactions, epoch=0)


def test_position_recalculation_state_is_immutable() -> None:
    state = PositionRecalculationState(
        portfolio_id="PB-001",
        security_id="SEC-001",
        epoch=4,
        watermark_date=date(2026, 4, 9),
        status="REPROCESSING",
    )

    with pytest.raises(FrozenInstanceError):
        state.epoch = 5  # type: ignore[misc]
