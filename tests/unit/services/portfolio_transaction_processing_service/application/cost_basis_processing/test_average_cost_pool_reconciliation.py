from dataclasses import replace
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.services.portfolio_transaction_processing_service.app.application.cost_basis_processing.average_cost_pool_reconciliation import (  # noqa: E501
    ReconcileAverageCostPoolsCommand,
    ReconcileAverageCostPoolsUseCase,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis.average_cost_pool_reconciliation import (  # noqa: E501
    AverageCostPoolKey,
    AverageCostPoolReconciliationAssessment,
    AverageCostPoolReconciliationStatus,
)


def assessment(
    key: AverageCostPoolKey,
    status: AverageCostPoolReconciliationStatus,
    *,
    reason_code: str | None = None,
) -> AverageCostPoolReconciliationAssessment:
    pool_quantity = (
        Decimal("10") if status is not AverageCostPoolReconciliationStatus.DRIFTED else None
    )
    return AverageCostPoolReconciliationAssessment(
        key=key,
        status=status,
        expected_source_count=2,
        expected_quantity=Decimal("10"),
        expected_cost_local=Decimal("100"),
        expected_cost_base=Decimal("120"),
        source_count=2,
        pool_quantity=pool_quantity,
        pool_cost_local=Decimal("100") if pool_quantity is not None else None,
        pool_cost_base=Decimal("120") if pool_quantity is not None else None,
        source_quantity=Decimal("10"),
        source_cost_local=Decimal("100"),
        source_cost_base=Decimal("120"),
        reason_code=reason_code,
    )


@pytest.mark.asyncio
async def test_use_case_runs_bounded_ordered_dry_run_and_returns_cursor() -> None:
    first = AverageCostPoolKey("P1", "S1")
    second = AverageCostPoolKey("P1", "S2")
    port = AsyncMock()
    port.list_candidates.return_value = (first, second)
    port.reconcile.side_effect = (
        assessment(first, AverageCostPoolReconciliationStatus.CURRENT),
        assessment(
            second,
            AverageCostPoolReconciliationStatus.DRIFTED,
            reason_code="pool_state_missing",
        ),
    )

    result = await ReconcileAverageCostPoolsUseCase(port).execute(
        ReconcileAverageCostPoolsCommand(limit=2, portfolio_id=" P1 ")
    )

    port.list_candidates.assert_awaited_once_with(portfolio_id="P1", after=None, limit=2)
    assert [call.kwargs for call in port.reconcile.await_args_list] == [
        {"key": first, "apply": False},
        {"key": second, "apply": False},
    ]
    assert result.current_count == 1
    assert result.drifted_count == 1
    assert result.reconciled_count == 0
    assert result.failed_count == 0
    assert result.next_cursor == second


@pytest.mark.asyncio
async def test_use_case_applies_each_key_and_omits_cursor_for_short_page() -> None:
    key = AverageCostPoolKey("P1", "S1")
    port = AsyncMock()
    port.list_candidates.return_value = (key,)
    port.reconcile.return_value = assessment(
        key,
        AverageCostPoolReconciliationStatus.RECONCILED,
    )

    result = await ReconcileAverageCostPoolsUseCase(port).execute(
        ReconcileAverageCostPoolsCommand(apply=True, limit=10)
    )

    port.reconcile.assert_awaited_once_with(key=key, apply=True)
    assert result.reconciled_count == 1
    assert result.next_cursor is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "keys",
    [
        (AverageCostPoolKey("P2", "S1"), AverageCostPoolKey("P1", "S1")),
        (AverageCostPoolKey("P1", "S1"), AverageCostPoolKey("P1", "S1")),
    ],
)
async def test_use_case_rejects_unordered_or_duplicate_candidate_contract(keys) -> None:
    port = AsyncMock()
    port.list_candidates.return_value = keys

    with pytest.raises(ValueError, match="unique and ordered"):
        await ReconcileAverageCostPoolsUseCase(port).execute(ReconcileAverageCostPoolsCommand())

    port.reconcile.assert_not_awaited()


@pytest.mark.parametrize("limit", [0, 1_001])
def test_command_rejects_unbounded_page_size(limit: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 1000"):
        ReconcileAverageCostPoolsCommand(limit=limit)


def test_assessment_rejects_equally_stale_pool_and_source_aggregate() -> None:
    with pytest.raises(ValueError, match="reconcile exactly"):
        AverageCostPoolReconciliationAssessment(
            key=AverageCostPoolKey("P1", "S1"),
            status=AverageCostPoolReconciliationStatus.CURRENT,
            expected_source_count=1,
            expected_quantity=Decimal("10"),
            expected_cost_local=Decimal("100"),
            expected_cost_base=Decimal("120"),
            source_count=1,
            pool_quantity=Decimal("9"),
            pool_cost_local=Decimal("100"),
            pool_cost_base=Decimal("120"),
            source_quantity=Decimal("9"),
            source_cost_local=Decimal("100"),
            source_cost_base=Decimal("120"),
        )


def test_assessment_requires_reason_for_drift_or_failure() -> None:
    with pytest.raises(ValueError, match="requires a reason"):
        assessment(
            AverageCostPoolKey("P1", "S1"),
            AverageCostPoolReconciliationStatus.DRIFTED,
        )


@pytest.mark.parametrize(
    ("portfolio_id", "security_id"),
    [("", "S1"), ("P1", "   ")],
)
def test_average_cost_pool_key_rejects_blank_identifiers(
    portfolio_id: str,
    security_id: str,
) -> None:
    with pytest.raises(ValueError, match="identifiers must not be blank"):
        AverageCostPoolKey(portfolio_id, security_id)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"expected_source_count": -1}, "source count must be nonnegative"),
        ({"source_count": -1}, "source count must be nonnegative"),
        ({"expected_quantity": Decimal("-1")}, "amounts must be nonnegative"),
        ({"reason_code": "unexpected_reason"}, "must not carry a failure reason"),
        (
            {
                "status": AverageCostPoolReconciliationStatus.DRIFTED,
                "reason_code": "reported_drift",
            },
            "must differ from replay truth",
        ),
    ],
)
def test_average_cost_pool_assessment_rejects_contradictory_state(
    changes: dict[str, object],
    message: str,
) -> None:
    current = assessment(
        AverageCostPoolKey("P1", "S1"),
        AverageCostPoolReconciliationStatus.CURRENT,
    )

    with pytest.raises(ValueError, match=message):
        replace(current, **changes)
