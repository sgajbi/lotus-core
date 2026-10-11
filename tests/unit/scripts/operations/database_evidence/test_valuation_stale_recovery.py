from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.operations.database_evidence import valuation_stale_recovery
from scripts.operations.database_evidence.contract import load_hot_path_scenario_catalog
from src.services.calculators.position_valuation_calculator.app.repositories.valuation_repository import (  # noqa: E501
    ValuationRepository,
)


@pytest.mark.asyncio
async def test_evidence_adapter_builds_real_tenant_scoped_reset_statement(monkeypatch) -> None:
    """Exercise the real repository and SQL builder, not PostgreSQL plan execution."""

    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.all.return_value = []
    result.fetchall.return_value = [(7,), (7,)]
    session.execute.return_value = result
    prefixes = []

    async def capture(_session, operation, *, statement_prefix):
        assert _session is session
        prefixes.append(statement_prefix)
        await operation(session)
        return [
            {
                "Plan": {
                    "Node Type": "Index Scan",
                    "Index Name": "test_plan_only",
                    "Actual Rows": 2,
                    "Actual Loops": 1,
                }
            }
        ]

    monkeypatch.setattr(
        valuation_stale_recovery, "capture_and_explain_rolled_back_statement", capture
    )
    scenarios = load_hot_path_scenario_catalog(
        Path("contracts/operations/database-hot-path-scenarios.v1.json")
    ).by_id()

    scan, reset = await valuation_stale_recovery.measure_valuation_stale_recovery(
        session,
        scan_scenario=scenarios["valuation_stale_scan"],
        reset_scenario=scenarios["valuation_stale_reset"],
        reset_job_scopes=(("tenant-b", 7), ("tenant-a", 7), ("tenant-a", 7)),
    )

    assert prefixes == ["SELECT", "UPDATE"]
    assert scan.scenario_id == "valuation_stale_scan"
    assert reset.scenario_id == "valuation_stale_reset"
    assert scan.status == reset.status == "passed"
    select_statement, reset_statement = [call.args[0] for call in session.execute.await_args_list]
    assert str(select_statement).startswith("SELECT")
    compiled = reset_statement.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    sql = str(compiled)
    assert (
        "(portfolio_valuation_jobs.tenant_id, portfolio_valuation_jobs.id) "
        "IN (('tenant-a', 7), ('tenant-b', 7))"
    ) in sql
    assert "portfolio_valuation_jobs.status = 'PROCESSING'" in sql
    assert "portfolio_valuation_jobs.valuation_lease_expires_at <= clock_timestamp()" in sql
    assert "status='PENDING'" in sql
    assert "valuation_claim_token=NULL" in sql


@pytest.mark.asyncio
async def test_real_reset_builder_reproduces_scalar_id_contract_failure() -> None:
    session = AsyncMock(spec=AsyncSession)

    with pytest.raises(TypeError, match="'int' object is not iterable"):
        await ValuationRepository(session)._reset_retryable_stale_jobs([7])

    session.execute.assert_not_awaited()
