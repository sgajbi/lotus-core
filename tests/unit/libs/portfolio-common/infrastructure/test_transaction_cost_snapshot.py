from datetime import UTC, datetime
from decimal import Decimal

import pytest
from portfolio_common.infrastructure.transaction_cost_snapshot import transaction_cost_snapshots


def test_transaction_cost_snapshots_preserve_aligned_component_order() -> None:
    first_updated_at = datetime(2026, 7, 29, 1, tzinfo=UTC)
    second_updated_at = datetime(2026, 7, 29, 2, tzinfo=UTC)

    snapshots = transaction_cost_snapshots(
        fee_types=["BROKERAGE", "STAMP_DUTY"],
        amounts=[Decimal("1.2500000000"), Decimal("0.7500000000")],
        currencies=["USD", "USD"],
        updated_ats=[first_updated_at, second_updated_at],
    )

    assert [(snapshot.fee_type, snapshot.amount) for snapshot in snapshots] == [
        ("BROKERAGE", Decimal("1.2500000000")),
        ("STAMP_DUTY", Decimal("0.7500000000")),
    ]
    assert [snapshot.updated_at for snapshot in snapshots] == [
        first_updated_at,
        second_updated_at,
    ]


def test_transaction_cost_snapshots_map_null_aggregate_row_to_empty_collection() -> None:
    assert (
        transaction_cost_snapshots(
            fee_types=None,
            amounts=None,
            currencies=None,
            updated_ats=None,
        )
        == ()
    )


@pytest.mark.parametrize(
    ("amounts", "currencies", "updated_ats"),
    [
        (None, ["USD"], [datetime(2026, 7, 29, tzinfo=UTC)]),
        ([Decimal("1")], [], [datetime(2026, 7, 29, tzinfo=UTC)]),
    ],
)
def test_transaction_cost_snapshots_fail_closed_for_misaligned_aggregates(
    amounts: list[Decimal] | None,
    currencies: list[str] | None,
    updated_ats: list[datetime] | None,
) -> None:
    with pytest.raises(ValueError, match="must be null together|lengths must match"):
        transaction_cost_snapshots(
            fee_types=["BROKERAGE"],
            amounts=amounts,
            currencies=currencies,
            updated_ats=updated_ats,
        )
