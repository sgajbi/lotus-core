"""Application and domain tests for lot-to-position parity evidence."""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.services.portfolio_transaction_processing_service.app.application.cost_basis_processing import (  # noqa: E501
    AuditLotPositionParityCommand,
    AuditLotPositionParityUseCase,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    LOT_QUANTITY_VS_POSITION_MISMATCH,
    LotPositionParityAssessment,
    LotPositionParityKey,
    LotPositionParityStatus,
)
from src.services.portfolio_transaction_processing_service.app.ports.cost_basis import (
    LotPositionParityPort,
)


def _assessment(
    portfolio_id: str,
    security_id: str,
    *,
    lot: str,
    position: str | None,
) -> LotPositionParityAssessment:
    matches = position is not None and Decimal(lot) == Decimal(position)
    return LotPositionParityAssessment(
        key=LotPositionParityKey(portfolio_id, security_id),
        epoch=3,
        lot_quantity=Decimal(lot),
        position_quantity=Decimal(position) if position is not None else None,
        status=LotPositionParityStatus.CURRENT if matches else LotPositionParityStatus.DRIFTED,
        finding_type=None if matches else LOT_QUANTITY_VS_POSITION_MISMATCH,
    )


@pytest.mark.asyncio
async def test_audit_returns_bounded_ordered_findings_and_cursor() -> None:
    port = AsyncMock(spec=LotPositionParityPort)
    port.assess_page.return_value = (
        _assessment("P-1", "S-1", lot="150", position="150"),
        _assessment("P-1", "S-2", lot="100", position="200"),
    )

    result = await AuditLotPositionParityUseCase(port).execute(
        AuditLotPositionParityCommand(portfolio_id=" P-1 ", limit=2)
    )

    assert (result.current_count, result.drifted_count) == (1, 1)
    assert result.assessments[1].finding_type == LOT_QUANTITY_VS_POSITION_MISMATCH
    assert result.next_cursor == LotPositionParityKey("P-1", "S-2")
    port.assess_page.assert_awaited_once_with(portfolio_id="P-1", after=None, limit=2)


@pytest.mark.asyncio
async def test_audit_rejects_unordered_adapter_results() -> None:
    port = AsyncMock(spec=LotPositionParityPort)
    port.assess_page.return_value = (
        _assessment("P-1", "S-2", lot="1", position="1"),
        _assessment("P-1", "S-1", lot="1", position="1"),
    )

    with pytest.raises(ValueError, match="unique and ordered"):
        await AuditLotPositionParityUseCase(port).execute(AuditLotPositionParityCommand())


@pytest.mark.parametrize("limit", [0, 1_001])
def test_audit_rejects_unbounded_page_sizes(limit: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 1000"):
        AuditLotPositionParityCommand(limit=limit)


def test_drifted_assessment_requires_governed_finding_type() -> None:
    with pytest.raises(ValueError, match="governed finding type"):
        LotPositionParityAssessment(
            key=LotPositionParityKey("P-1", "S-1"),
            epoch=0,
            lot_quantity=Decimal("1"),
            position_quantity=Decimal("2"),
            status=LotPositionParityStatus.DRIFTED,
        )


def test_missing_position_is_governed_lot_position_drift() -> None:
    assessment = LotPositionParityAssessment(
        key=LotPositionParityKey("P-1", "S-1"),
        epoch=0,
        lot_quantity=Decimal("1"),
        position_quantity=None,
        status=LotPositionParityStatus.DRIFTED,
        finding_type=LOT_QUANTITY_VS_POSITION_MISMATCH,
    )

    assert assessment.status is LotPositionParityStatus.DRIFTED
    assert assessment.position_quantity is None


def test_exact_parity_cannot_be_classified_as_drifted() -> None:
    with pytest.raises(ValueError, match="governed finding type"):
        LotPositionParityAssessment(
            key=LotPositionParityKey("P-1", "S-1"),
            epoch=0,
            lot_quantity=Decimal("1"),
            position_quantity=Decimal("1"),
            status=LotPositionParityStatus.DRIFTED,
            finding_type=LOT_QUANTITY_VS_POSITION_MISMATCH,
        )


@pytest.mark.parametrize(
    ("portfolio_id", "security_id"),
    [(" ", "S-1"), ("P-1", "\t")],
)
def test_parity_key_rejects_blank_identifiers(
    portfolio_id: str,
    security_id: str,
) -> None:
    with pytest.raises(ValueError, match="identifiers must not be blank"):
        LotPositionParityKey(portfolio_id, security_id)


@pytest.mark.parametrize(
    ("epoch", "lot_quantity", "message"),
    [
        (-1, Decimal("1"), "epoch must be nonnegative"),
        (0, Decimal("-0.0000000001"), "Lot quantity must be nonnegative"),
    ],
)
def test_parity_assessment_rejects_invalid_durable_quantities(
    epoch: int,
    lot_quantity: Decimal,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        LotPositionParityAssessment(
            key=LotPositionParityKey("P-1", "S-1"),
            epoch=epoch,
            lot_quantity=lot_quantity,
            position_quantity=Decimal("1"),
            status=LotPositionParityStatus.CURRENT,
        )


@pytest.mark.parametrize(
    ("position_quantity", "finding_type"),
    [
        (Decimal("2"), None),
        (Decimal("1"), LOT_QUANTITY_VS_POSITION_MISMATCH),
    ],
)
def test_current_assessment_requires_exact_unqualified_parity(
    position_quantity: Decimal,
    finding_type: str | None,
) -> None:
    with pytest.raises(ValueError, match="must reconcile exactly"):
        LotPositionParityAssessment(
            key=LotPositionParityKey("P-1", "S-1"),
            epoch=0,
            lot_quantity=Decimal("1"),
            position_quantity=position_quantity,
            status=LotPositionParityStatus.CURRENT,
            finding_type=finding_type,
        )
