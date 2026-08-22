"""Tests for source-safe lot-position parity report rendering."""

from decimal import Decimal

from scripts.operations.audit_lot_position_parity import build_report
from src.services.portfolio_transaction_processing_service.app.application import (
    AuditLotPositionParityResult,
)
from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    LOT_QUANTITY_VS_POSITION_MISMATCH,
    LotPositionParityAssessment,
    LotPositionParityKey,
    LotPositionParityStatus,
)


def test_report_exposes_stable_mismatch_without_transaction_or_lot_identifiers() -> None:
    result = AuditLotPositionParityResult(
        assessments=(
            LotPositionParityAssessment(
                key=LotPositionParityKey("PORT-1", "SEC-1"),
                epoch=2,
                lot_quantity=Decimal("75"),
                position_quantity=Decimal("150"),
                status=LotPositionParityStatus.DRIFTED,
                finding_type=LOT_QUANTITY_VS_POSITION_MISMATCH,
            ),
        ),
        next_cursor=None,
    )

    report = build_report(result)

    assert report["summary"] == {
        "candidate_count": 1,
        "current_count": 0,
        "drifted_count": 1,
    }
    assert report["assessments"][0]["finding_type"] == (
        LOT_QUANTITY_VS_POSITION_MISMATCH
    )
    assert "transaction_id" not in report["assessments"][0]
    assert "lot_id" not in report["assessments"][0]
