import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from portfolio_common import db as db_module
from portfolio_common.database_runtime_identity import database_runtime_identity
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from scripts.operations import reconcile_average_cost_pools as operator
from scripts.operations.reconcile_average_cost_pools import SCHEMA_VERSION, build_report, exit_code
from src.services.portfolio_transaction_processing_service.app.application import (
    ReconcileAverageCostPoolsResult,
)
from src.services.portfolio_transaction_processing_service.app.domain import (
    AverageCostPoolKey,
    AverageCostPoolReconciliationAssessment,
    AverageCostPoolReconciliationStatus,
)
from src.services.portfolio_transaction_processing_service.app.runtime import dependency_composition


def _assessment(
    status: AverageCostPoolReconciliationStatus,
    *,
    reason_code: str | None = None,
) -> AverageCostPoolReconciliationAssessment:
    key = AverageCostPoolKey("P1", "S1")
    pool_quantity = (
        Decimal("9") if status is AverageCostPoolReconciliationStatus.DRIFTED else Decimal("10")
    )
    return AverageCostPoolReconciliationAssessment(
        key=key,
        status=status,
        expected_source_count=1,
        expected_quantity=Decimal("10"),
        expected_cost_local=Decimal("100"),
        expected_cost_base=Decimal("120"),
        source_count=1,
        pool_quantity=pool_quantity,
        pool_cost_local=Decimal("100"),
        pool_cost_base=Decimal("120"),
        source_quantity=Decimal("10"),
        source_cost_local=Decimal("100"),
        source_cost_base=Decimal("120"),
        reason_code=reason_code,
    )


def test_report_is_decimal_safe_and_exposes_resume_cursor() -> None:
    result = ReconcileAverageCostPoolsResult(
        apply=True,
        assessments=(_assessment(AverageCostPoolReconciliationStatus.RECONCILED),),
        next_cursor=AverageCostPoolKey("P1", "S1"),
    )

    report = build_report(result)

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["generated_at_utc"].endswith("+00:00")
    assert report["mode"] == "apply"
    assert report["summary"] == {
        "candidate_count": 1,
        "current_count": 0,
        "drifted_count": 0,
        "reconciled_count": 1,
        "failed_count": 0,
    }
    assert report["next_cursor"] == {"portfolio_id": "P1", "security_id": "S1"}
    assert report["assessments"][0]["expected_quantity"] == "10"
    assert report["assessments"][0]["status"] == "reconciled"
    assert exit_code(report) == 0


def test_dry_run_drift_and_failure_use_distinct_nonzero_exit_codes() -> None:
    drift = build_report(
        ReconcileAverageCostPoolsResult(
            apply=False,
            assessments=(
                _assessment(
                    AverageCostPoolReconciliationStatus.DRIFTED,
                    reason_code="pool_or_source_aggregate_mismatch",
                ),
            ),
            next_cursor=None,
        )
    )
    failure_assessment = _assessment(
        AverageCostPoolReconciliationStatus.FAILED,
        reason_code="average_cost_reconciliation_failed",
    )
    failure = build_report(
        ReconcileAverageCostPoolsResult(
            apply=True,
            assessments=(failure_assessment,),
            next_cursor=None,
        )
    )

    assert exit_code(drift) == 1
    assert exit_code(failure) == 2


@pytest.fixture
def owned_provider_probe(monkeypatch: pytest.MonkeyPatch):
    """Exercise real construction/composition, replacing only the database I/O adapter."""
    probe = SimpleNamespace(
        engines=[],
        disposals=[],
        factories=[],
        status=AverageCostPoolReconciliationStatus.CURRENT,
        apply=False,
        failure_stage=None,
        identity=database_runtime_identity(),
        foreign_engine=object(),
        foreign_factory=object(),
    )
    governed_create_engine = db_module.create_async_database_engine
    real_dispose = AsyncEngine.dispose

    async def dispose_owned(engine):
        assert database_runtime_identity() == "average-cost-reconciliation"
        probe.disposals.append(engine)
        await real_dispose(engine)

    def create_owned_engine(*, runtime_identity):
        assert runtime_identity == "average-cost-reconciliation"
        assert database_runtime_identity() == runtime_identity
        engine = governed_create_engine(
            runtime_identity=runtime_identity,
            database_url="postgresql+asyncpg://unused:unused@localhost/unused",
        )
        probe.engines.append(engine)
        return engine

    def reject_foreign_provider(*args, **kwargs):
        pytest.fail("operator must not access the shared database provider or connect")

    class NoIOReconciliation:
        def __init__(self, *, session_factory, rebuild_planner):
            assert session_factory.kw == {
                "bind": probe.engines[-1],
                "autocommit": False,
                "autoflush": False,
                "expire_on_commit": False,
            }
            assert session_factory.class_ is AsyncSession
            probe.factories.append(session_factory)
            if probe.failure_stage == "composition":
                raise ValueError("reconciliation composition refused")

        async def list_candidates(self, *, portfolio_id, after, limit):
            assert database_runtime_identity() == "average-cost-reconciliation"
            assert (portfolio_id, after, limit) == ("P1", AverageCostPoolKey("P0", "S0"), 1)
            return (AverageCostPoolKey("P1", "S1"),)

        async def reconcile(self, *, key, apply):
            assert database_runtime_identity() == "average-cost-reconciliation"
            assert key == AverageCostPoolKey("P1", "S1")
            assert apply is probe.apply
            if probe.failure_stage == "execution":
                raise ValueError("reconciliation execution refused")
            reason_codes = {
                AverageCostPoolReconciliationStatus.DRIFTED: "pool_or_source_aggregate_mismatch",
                AverageCostPoolReconciliationStatus.FAILED: "average_cost_reconciliation_failed",
            }
            return _assessment(probe.status, reason_code=reason_codes.get(probe.status))

    monkeypatch.setattr(db_module, "_async_engine", probe.foreign_engine)
    monkeypatch.setattr(db_module, "_async_session_factory", probe.foreign_factory)
    monkeypatch.setattr(db_module, "get_async_engine", reject_foreign_provider)
    monkeypatch.setattr(db_module, "get_async_session_factory", reject_foreign_provider)
    monkeypatch.setattr(
        dependency_composition, "get_async_session_factory", reject_foreign_provider
    )
    monkeypatch.setattr(operator, "get_async_engine", reject_foreign_provider, raising=False)
    monkeypatch.setattr(
        operator, "create_async_database_engine", create_owned_engine, raising=False
    )
    monkeypatch.setattr(AsyncEngine, "dispose", dispose_owned)
    monkeypatch.setattr(AsyncEngine, "connect", reject_foreign_provider)
    monkeypatch.setattr(
        dependency_composition, "SqlAlchemyAverageCostPoolReconciliationAdapter", NoIOReconciliation
    )
    return probe


def _assert_provider_ownership(probe) -> None:
    assert probe.disposals == probe.engines
    assert len(probe.factories) == len(probe.engines)
    assert database_runtime_identity() == probe.identity
    assert db_module._async_engine is probe.foreign_engine
    assert db_module._async_session_factory is probe.foreign_factory


@pytest.mark.parametrize(
    ("status", "apply", "expected_exit"),
    [
        (AverageCostPoolReconciliationStatus.CURRENT, False, 0),
        (AverageCostPoolReconciliationStatus.DRIFTED, False, 1),
        (AverageCostPoolReconciliationStatus.RECONCILED, True, 0),
        (AverageCostPoolReconciliationStatus.FAILED, True, 2),
    ],
)
def test_repeated_main_owns_provider_and_preserves_cli_contract(
    monkeypatch, capsys, tmp_path, owned_provider_probe, status, apply, expected_exit
) -> None:
    probe = owned_provider_probe
    probe.status, probe.apply = status, apply
    output = tmp_path / "reports" / "reconciliation.json"
    argv = [
        "reconcile_average_cost_pools",
        "--portfolio-id",
        "P1",
        "--limit",
        "1",
        "--after-portfolio-id",
        "P0",
        "--after-security-id",
        "S0",
        "--output",
        str(output),
    ]
    if apply:
        argv.append("--apply")
    monkeypatch.setattr("sys.argv", argv)

    for _ in range(2):
        assert operator.main() == expected_exit
        report = json.loads(capsys.readouterr().out)
        assert report == json.loads(output.read_text(encoding="utf-8"))
        assert report["schema_version"] == SCHEMA_VERSION
        assert report["mode"] == ("apply" if apply else "dry_run")
        assert report["summary"]["candidate_count"] == 1
        assert report["summary"][f"{status.value}_count"] == 1
        assert report["next_cursor"] == {"portfolio_id": "P1", "security_id": "S1"}
        assert report["assessments"][0]["expected_cost_local"] == "100"
        assert report["assessments"][0]["expected_cost_base"] == "120"
        _assert_provider_ownership(probe)
    assert probe.engines[0] is not probe.engines[1]
    assert probe.factories[0] is not probe.factories[1]


@pytest.mark.parametrize("failure_stage", ["composition", "execution"])
def test_repeated_main_disposes_only_owned_provider_on_failure(
    monkeypatch, capsys, tmp_path, owned_provider_probe, failure_stage
) -> None:
    probe = owned_provider_probe
    probe.failure_stage = failure_stage
    output = tmp_path / "must-not-exist.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "reconcile_average_cost_pools",
            "--portfolio-id",
            "P1",
            "--limit",
            "1",
            "--after-portfolio-id",
            "P0",
            "--after-security-id",
            "S0",
            "--output",
            str(output),
        ],
    )
    for _ in range(2):
        with pytest.raises(ValueError, match=f"reconciliation {failure_stage} refused"):
            operator.main()
        assert capsys.readouterr().out == ""
        assert not output.exists()
        _assert_provider_ownership(probe)
    assert probe.engines[0] is not probe.engines[1]
