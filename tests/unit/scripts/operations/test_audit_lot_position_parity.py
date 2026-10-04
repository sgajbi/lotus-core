"""Tests for source-safe lot-position parity report rendering."""

from argparse import Namespace
from decimal import Decimal

import pytest
from portfolio_common import db as db_module
from portfolio_common.database_runtime_identity import (
    NON_CERTIFYING_DATABASE_RUNTIME_IDENTITIES,
    database_runtime_identity,
)
from portfolio_common.database_runtime_profile import (
    DATABASE_RUNTIME_COHORT_BY_IDENTITY,
    DatabaseRuntimeCohort,
)
from sqlalchemy.ext.asyncio import AsyncEngine

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
@pytest.mark.parametrize("execution_fails", [False, True])
async def test_run_owns_fresh_registered_engine_and_disposes_on_every_outcome(
    monkeypatch: pytest.MonkeyPatch, execution_fails: bool
) -> None:
    original_identity = database_runtime_identity()
    engines = []
    disposals = []
    real_dispose = AsyncEngine.dispose
    governed_create_engine = db_module.create_async_database_engine

    async def dispose_owned_engine(engine):
        disposals.append(engine)
        await real_dispose(engine)

    monkeypatch.setattr(AsyncEngine, "dispose", dispose_owned_engine)

    def create_owned_engine(*, runtime_identity):
        assert runtime_identity == "lot-position-parity-audit"
        assert database_runtime_identity() == runtime_identity
        # Real engine/factory binding, without allocating a database connection.
        engine = governed_create_engine(
            runtime_identity=runtime_identity,
            database_url="postgresql+asyncpg://unused:unused@localhost/unused",
        )
        engines.append(engine)
        return engine

    def reject_global_access():
        pytest.fail("audit must not borrow or dispose the process-global database provider")

    monkeypatch.setattr(db_module, "get_async_engine", reject_global_access)
    monkeypatch.setattr(db_module, "get_async_session_factory", reject_global_access)
    monkeypatch.setattr(
        audit_lot_position_parity, "get_async_engine", reject_global_access, raising=False
    )
    monkeypatch.setattr(
        audit_lot_position_parity,
        "create_async_database_engine",
        create_owned_engine,
        raising=False,
    )

    class _UseCase:
        def __init__(self, *, session_factory):
            assert session_factory.kw["bind"] is engines[-1]
            assert session_factory.kw["expire_on_commit"] is False
            assert session_factory.kw["autoflush"] is False
            assert session_factory.kw["autocommit"] is False

        async def execute(self, command):
            assert database_runtime_identity() == "lot-position-parity-audit"
            assert command.limit == 25
            assert command.portfolio_id == "PORT-1"
            assert command.after == LotPositionParityKey("PORT-0", "SEC-0")
            if execution_fails:
                raise ValueError("audit execution refused")
            return AuditLotPositionParityResult(
                assessments=(),
                next_cursor=None,
            )

    monkeypatch.setattr(
        audit_lot_position_parity,
        "build_audit_lot_position_parity_use_case",
        _UseCase,
    )
    args = Namespace(
        portfolio_id="PORT-1",
        limit=25,
        after_portfolio_id="PORT-0",
        after_security_id="SEC-0",
        output=None,
    )

    for _ in range(2):
        if execution_fails:
            with pytest.raises(ValueError, match="audit execution refused"):
                await audit_lot_position_parity.run(args)
        else:
            report = await audit_lot_position_parity.run(args)
            assert report["summary"]["candidate_count"] == 0
            assert audit_lot_position_parity.report_exit_code(report) == 0
        assert disposals == engines
    assert engines[0] is not engines[1]
    assert database_runtime_identity() == original_identity
    assert (
        DATABASE_RUNTIME_COHORT_BY_IDENTITY["lot-position-parity-audit"]
        is DatabaseRuntimeCohort.OPERATOR
    )
    assert "lot-position-parity-audit" not in NON_CERTIFYING_DATABASE_RUNTIME_IDENTITIES
