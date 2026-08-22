"""Tests for source-safe lot-position parity report rendering."""

from argparse import Namespace
from decimal import Decimal

import pytest
from portfolio_common.database_runtime_identity import (
    NON_CERTIFYING_DATABASE_RUNTIME_IDENTITIES,
    database_runtime_identity,
)
from portfolio_common.database_runtime_profile import (
    DATABASE_RUNTIME_COHORT_BY_IDENTITY,
    DatabaseRuntimeCohort,
)

from scripts.operations import audit_lot_position_parity
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
    assert report["assessments"][0]["finding_type"] == (LOT_QUANTITY_VS_POSITION_MISMATCH)
    assert "transaction_id" not in report["assessments"][0]
    assert "lot_id" not in report["assessments"][0]


@pytest.mark.asyncio
async def test_run_uses_registered_operator_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    disposed = False

    class _UseCase:
        async def execute(self, command):
            assert database_runtime_identity() == "lot-position-parity-audit"
            assert command.limit == 25
            return AuditLotPositionParityResult(
                assessments=(),
                next_cursor=None,
            )

    class _Engine:
        async def dispose(self) -> None:
            nonlocal disposed
            disposed = True

    monkeypatch.setattr(
        audit_lot_position_parity,
        "build_audit_lot_position_parity_use_case",
        _UseCase,
    )
    monkeypatch.setattr(
        audit_lot_position_parity,
        "get_async_engine",
        lambda: _Engine(),
    )
    args = Namespace(
        portfolio_id="PORT-1",
        limit=25,
        after_portfolio_id=None,
        after_security_id=None,
        output=None,
    )

    report = await audit_lot_position_parity.run(args)

    assert report["summary"]["candidate_count"] == 0
    assert audit_lot_position_parity.report_exit_code(report) == 0
    assert disposed is True
    assert (
        DATABASE_RUNTIME_COHORT_BY_IDENTITY["lot-position-parity-audit"]
        is DatabaseRuntimeCohort.OPERATOR
    )
    assert "lot-position-parity-audit" not in NON_CERTIFYING_DATABASE_RUNTIME_IDENTITIES
