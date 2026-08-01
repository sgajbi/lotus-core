"""Domain tests for deterministic position-timeseries calculation."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import cast

import pytest
from portfolio_common.domain.calculation_lineage import (
    CalculationLineage,
    build_calculation_lineage,
)

from src.services.portfolio_derived_state_service.app.domain.position_timeseries.calculator import (
    PositionSnapshotNotValuedError,
    calculate_position_timeseries,
)
from src.services.portfolio_derived_state_service.app.domain.position_timeseries.models import (
    PositionCashflowRecord,
    PositionSnapshotRecord,
)

BUSINESS_DATE = date(2025, 7, 29)


@pytest.fixture
def current_snapshot() -> PositionSnapshotRecord:
    """Return a valued end-of-day position state."""

    return PositionSnapshotRecord(
        portfolio_id="P1",
        security_id="S1",
        date=BUSINESS_DATE,
        epoch=5,
        quantity=Decimal("100"),
        cost_basis_local=Decimal("10000"),
        market_value_local=Decimal("12000"),
    )


@pytest.fixture
def previous_snapshot() -> PositionSnapshotRecord:
    """Return the immediately preceding valued position state."""

    return PositionSnapshotRecord(
        portfolio_id="P1",
        security_id="S1",
        date=date(2025, 7, 28),
        epoch=5,
        quantity=Decimal("90"),
        cost_basis_local=Decimal("9000"),
        market_value_local=Decimal("11500"),
    )


def _cashflow(
    *,
    amount: Decimal,
    classification: str,
    timing: str,
    is_position_flow: bool,
    is_portfolio_flow: bool,
    transaction_id: str = "T1",
    calculation_lineage: CalculationLineage | None = None,
) -> PositionCashflowRecord:
    return PositionCashflowRecord(
        transaction_id=transaction_id,
        cashflow_date=BUSINESS_DATE,
        epoch=5,
        amount=amount,
        classification=classification,
        timing=timing,
        is_position_flow=is_position_flow,
        is_portfolio_flow=is_portfolio_flow,
        calculation_lineage=calculation_lineage,
    )


def _source_lineage(source_revision: str) -> CalculationLineage:
    return build_calculation_lineage(
        algorithm_id="upstream-financial-calculation",
        algorithm_version=1,
        intermediate_precision=28,
        input_payload={"source_revision": source_revision},
        output_payload={"amount": Decimal("100")},
    )


def test_calculation_uses_requested_epoch(
    current_snapshot: PositionSnapshotRecord,
    previous_snapshot: PositionSnapshotRecord,
) -> None:
    record = calculate_position_timeseries(
        current_snapshot=current_snapshot,
        previous_snapshot=previous_snapshot,
        cashflows=[],
        epoch=8,
    )

    assert record.epoch == 8


def test_first_position_day_has_zero_beginning_market_value(
    current_snapshot: PositionSnapshotRecord,
) -> None:
    record = calculate_position_timeseries(
        current_snapshot=current_snapshot,
        previous_snapshot=None,
        cashflows=[],
        epoch=5,
    )

    assert record.bod_market_value == Decimal("0")


@pytest.mark.parametrize(
    ("missing_boundary", "expected_message"),
    [
        ("current", "end-of-day position snapshot"),
        ("previous", "beginning position snapshot"),
    ],
)
def test_calculation_rejects_unvalued_numeric_boundaries(
    current_snapshot: PositionSnapshotRecord,
    previous_snapshot: PositionSnapshotRecord,
    missing_boundary: str,
    expected_message: str,
) -> None:
    current = current_snapshot
    previous = previous_snapshot
    if missing_boundary == "current":
        current = replace(current, market_value_local=None)
    else:
        previous = replace(previous, market_value_local=None)

    with pytest.raises(PositionSnapshotNotValuedError, match=expected_message):
        calculate_position_timeseries(
            current_snapshot=current,
            previous_snapshot=previous,
            cashflows=[],
            epoch=5,
        )


def test_calculation_separates_position_and_portfolio_cashflows(
    current_snapshot: PositionSnapshotRecord,
    previous_snapshot: PositionSnapshotRecord,
) -> None:
    cashflows = [
        _cashflow(
            amount=Decimal("1000"),
            timing="BOD",
            classification="CASHFLOW_IN",
            is_position_flow=True,
            is_portfolio_flow=False,
        ),
        _cashflow(
            amount=Decimal("-50"),
            timing="EOD",
            classification=" expense ",
            is_position_flow=True,
            is_portfolio_flow=True,
            transaction_id="T2",
        ),
    ]

    record = calculate_position_timeseries(
        current_snapshot=current_snapshot,
        previous_snapshot=previous_snapshot,
        cashflows=cashflows,
        epoch=5,
    )

    assert record.bod_market_value == Decimal("11500")
    assert record.eod_market_value == Decimal("12000")
    assert record.bod_cashflow_position == Decimal("1000")
    assert record.bod_cashflow_portfolio == Decimal("0")
    assert record.eod_cashflow_position == Decimal("-50")
    assert record.eod_cashflow_portfolio == Decimal("-50")
    assert record.fees == Decimal("50")
    assert record.calculation_lineage is not None
    assert record.calculation_lineage.algorithm_id == "position-timeseries-materialization"
    assert record.calculation_lineage.numeric_output_policy is not None
    assert record.calculation_lineage.numeric_output_policy.policy_id == (
        "position-timeseries-ledger-output@1.0.0"
    )


def test_position_timeseries_lineage_is_deterministic_and_material_input_sensitive(
    current_snapshot: PositionSnapshotRecord,
    previous_snapshot: PositionSnapshotRecord,
) -> None:
    baseline = calculate_position_timeseries(
        current_snapshot=current_snapshot,
        previous_snapshot=previous_snapshot,
        cashflows=[],
        epoch=5,
    )
    repeated = calculate_position_timeseries(
        current_snapshot=current_snapshot,
        previous_snapshot=previous_snapshot,
        cashflows=[],
        epoch=5,
    )
    changed = calculate_position_timeseries(
        current_snapshot=replace(current_snapshot, market_value_local=Decimal("12001")),
        previous_snapshot=previous_snapshot,
        cashflows=[],
        epoch=5,
    )

    assert repeated.calculation_lineage == baseline.calculation_lineage
    assert baseline.calculation_lineage is not None
    assert changed.calculation_lineage is not None
    assert baseline.calculation_lineage.input_content_hash != (
        changed.calculation_lineage.input_content_hash
    )
    assert baseline.calculation_lineage.output_content_hash != (
        changed.calculation_lineage.output_content_hash
    )


@pytest.mark.parametrize("source_kind", ["current_snapshot", "previous_snapshot", "cashflow"])
def test_position_timeseries_lineage_binds_upstream_financial_lineage(
    current_snapshot: PositionSnapshotRecord,
    previous_snapshot: PositionSnapshotRecord,
    source_kind: str,
) -> None:
    baseline_current = current_snapshot
    changed_current = current_snapshot
    baseline_previous = previous_snapshot
    changed_previous = previous_snapshot
    baseline_cashflows: list[PositionCashflowRecord] = []
    changed_cashflows: list[PositionCashflowRecord] = []
    if source_kind == "current_snapshot":
        baseline_current = replace(
            current_snapshot,
            calculation_lineage=_source_lineage("valuation-revision-1"),
        )
        changed_current = replace(
            current_snapshot,
            calculation_lineage=_source_lineage("valuation-revision-2"),
        )
    elif source_kind == "previous_snapshot":
        baseline_previous = replace(
            previous_snapshot,
            calculation_lineage=_source_lineage("valuation-revision-1"),
        )
        changed_previous = replace(
            previous_snapshot,
            calculation_lineage=_source_lineage("valuation-revision-2"),
        )
    else:
        baseline_cashflows = [
            _cashflow(
                amount=Decimal("100"),
                timing="EOD",
                classification="INCOME",
                is_position_flow=True,
                is_portfolio_flow=False,
                calculation_lineage=_source_lineage("cashflow-revision-1"),
            )
        ]
        changed_cashflows = [
            _cashflow(
                amount=Decimal("100"),
                timing="EOD",
                classification="INCOME",
                is_position_flow=True,
                is_portfolio_flow=False,
                calculation_lineage=_source_lineage("cashflow-revision-2"),
            )
        ]

    baseline = calculate_position_timeseries(
        current_snapshot=baseline_current,
        previous_snapshot=baseline_previous,
        cashflows=baseline_cashflows,
        epoch=5,
    )
    changed = calculate_position_timeseries(
        current_snapshot=changed_current,
        previous_snapshot=changed_previous,
        cashflows=changed_cashflows,
        epoch=5,
    )

    baseline_lineage = baseline.calculation_lineage
    changed_lineage = changed.calculation_lineage
    assert baseline_lineage is not None
    assert changed_lineage is not None
    assert replace(baseline, calculation_lineage=None) == replace(changed, calculation_lineage=None)
    assert baseline_lineage.input_content_hash != changed_lineage.input_content_hash
    assert baseline_lineage.output_content_hash != changed_lineage.output_content_hash


def test_calculation_defensively_normalizes_numeric_text_and_blank_amounts() -> None:
    current_snapshot = PositionSnapshotRecord(
        portfolio_id="P1",
        security_id="S1",
        date=BUSINESS_DATE,
        epoch=6,
        quantity=cast(Decimal, "100"),
        cost_basis_local=cast(Decimal, "10000"),
        market_value_local=cast(Decimal, "12000"),
    )
    previous_snapshot = PositionSnapshotRecord(
        portfolio_id="P1",
        security_id="S1",
        date=date(2025, 7, 28),
        epoch=6,
        quantity=Decimal("90"),
        cost_basis_local=Decimal("9000"),
        market_value_local=cast(Decimal, "11500"),
    )
    cashflows = [
        _cashflow(
            amount=cast(Decimal, "1000"),
            timing="BOD",
            classification="CASHFLOW_IN",
            is_position_flow=True,
            is_portfolio_flow=False,
        ),
        _cashflow(
            amount=cast(Decimal, " "),
            timing="EOD",
            classification="EXPENSE",
            is_position_flow=True,
            is_portfolio_flow=True,
            transaction_id="T2",
        ),
    ]

    record = calculate_position_timeseries(
        current_snapshot=current_snapshot,
        previous_snapshot=previous_snapshot,
        cashflows=cashflows,
        epoch=6,
    )

    assert record.bod_market_value == Decimal("11500")
    assert record.eod_market_value == Decimal("12000")
    assert record.cost == Decimal("100")
    assert record.bod_cashflow_position == Decimal("1000")
    assert record.eod_cashflow_portfolio == Decimal("0")
    assert record.fees == Decimal("0")


def test_zero_quantity_produces_zero_average_cost(
    current_snapshot: PositionSnapshotRecord,
    previous_snapshot: PositionSnapshotRecord,
) -> None:
    zero_quantity_snapshot = PositionSnapshotRecord(
        portfolio_id=current_snapshot.portfolio_id,
        security_id=current_snapshot.security_id,
        date=current_snapshot.date,
        epoch=current_snapshot.epoch,
        quantity=Decimal("0"),
        cost_basis_local=Decimal("10000"),
        market_value_local=Decimal("0"),
    )

    record = calculate_position_timeseries(
        current_snapshot=zero_quantity_snapshot,
        previous_snapshot=previous_snapshot,
        cashflows=[],
        epoch=8,
    )

    assert record.quantity == Decimal("0")
    assert record.cost == Decimal("0")


def test_repeating_average_cost_is_normalized_for_exact_persistence(
    previous_snapshot: PositionSnapshotRecord,
) -> None:
    current_snapshot = PositionSnapshotRecord(
        portfolio_id="P1",
        security_id="S1",
        date=BUSINESS_DATE,
        epoch=8,
        quantity=Decimal("3"),
        cost_basis_local=Decimal("100"),
        market_value_local=Decimal("100"),
    )

    record = calculate_position_timeseries(
        current_snapshot=current_snapshot,
        previous_snapshot=previous_snapshot,
        cashflows=[],
        epoch=8,
    )

    assert record.cost == Decimal("33.3333333333")


def test_cashflow_bucket_overflow_fails_closed(
    current_snapshot: PositionSnapshotRecord,
    previous_snapshot: PositionSnapshotRecord,
) -> None:
    cashflows = [
        _cashflow(
            amount=Decimal("60000000"),
            timing="BOD",
            classification="CASHFLOW_IN",
            is_position_flow=True,
            is_portfolio_flow=False,
            transaction_id=f"T{index}",
        )
        for index in range(2)
    ]

    with pytest.raises(ValueError, match="position-timeseries-ledger-output@1.0.0"):
        calculate_position_timeseries(
            current_snapshot=current_snapshot,
            previous_snapshot=previous_snapshot,
            cashflows=cashflows,
            epoch=8,
        )


def test_cashflow_timing_is_canonicalized_before_bucketing(
    current_snapshot: PositionSnapshotRecord,
    previous_snapshot: PositionSnapshotRecord,
) -> None:
    cashflows = [
        _cashflow(
            amount=Decimal("1000"),
            timing=" bod ",
            classification="CASHFLOW_IN",
            is_position_flow=True,
            is_portfolio_flow=True,
        )
    ]

    record = calculate_position_timeseries(
        current_snapshot=current_snapshot,
        previous_snapshot=previous_snapshot,
        cashflows=cashflows,
        epoch=7,
    )

    assert record.bod_cashflow_position == Decimal("1000")
    assert record.eod_cashflow_position == Decimal("0")
    assert record.bod_cashflow_portfolio == Decimal("1000")
    assert record.eod_cashflow_portfolio == Decimal("0")


def test_product_leg_signs_are_normalized_for_attribution(
    current_snapshot: PositionSnapshotRecord,
    previous_snapshot: PositionSnapshotRecord,
) -> None:
    cashflows = [
        _cashflow(
            amount=Decimal("-1000"),
            classification=" investment_outflow ",
            timing="BOD",
            is_position_flow=True,
            is_portfolio_flow=False,
        ),
        _cashflow(
            amount=Decimal("250"),
            classification="INCOME",
            timing="EOD",
            is_position_flow=True,
            is_portfolio_flow=False,
            transaction_id="T2",
        ),
        _cashflow(
            amount=Decimal("-1000"),
            classification="TRANSFER",
            timing="EOD",
            is_position_flow=True,
            is_portfolio_flow=False,
            transaction_id="T3",
        ),
    ]

    record = calculate_position_timeseries(
        current_snapshot=current_snapshot,
        previous_snapshot=previous_snapshot,
        cashflows=cashflows,
        epoch=5,
    )

    assert record.bod_cashflow_position == Decimal("1000")
    assert record.eod_cashflow_position == Decimal("-1250")


def test_expense_fees_do_not_reclassify_external_withdrawals(
    current_snapshot: PositionSnapshotRecord,
    previous_snapshot: PositionSnapshotRecord,
) -> None:
    cashflows = [
        _cashflow(
            amount=Decimal("-25000"),
            classification="CASHFLOW_OUT",
            timing="EOD",
            is_position_flow=True,
            is_portfolio_flow=True,
        ),
        _cashflow(
            amount=Decimal("-275"),
            classification="EXPENSE",
            timing="EOD",
            is_position_flow=True,
            is_portfolio_flow=True,
            transaction_id="T2",
        ),
    ]

    record = calculate_position_timeseries(
        current_snapshot=current_snapshot,
        previous_snapshot=previous_snapshot,
        cashflows=cashflows,
        epoch=14,
    )

    assert record.eod_cashflow_portfolio == Decimal("-25275")
    assert record.fees == Decimal("275")
