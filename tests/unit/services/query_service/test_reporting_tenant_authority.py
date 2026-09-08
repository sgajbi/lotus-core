"""Tenant authority on the reporting read surface (#798 tranche B).

Tranche A bound portfolio discovery and detail to the admitted tenant. Its
sibling reporting routes read the same `portfolios` table with the predicate
absent, so a caller with any nonblank `X-Tenant-Id` received any portfolio.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from portfolio_common.domain.tenant import TenantContext, TenantId
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.repositories.portfolio_existence import (
    portfolio_exists_for_tenant,
)
from src.services.query_service.app.repositories.reporting_repository import (
    ReportingRepository,
)
from tests.test_support.tenant import TEST_TENANT_CONTEXT

QUERY_SERVICE_APP = (
    Path(__file__).resolve().parents[4] / "src" / "services" / "query_service" / "app"
)
# The admitted tenant is the repository's shared fixture, so these tests and the
# router tests speak about the same identity. FOREIGN is deliberately a value no
# fixture seeds, so a leak cannot be masked by a coincidental match.
TENANT = TEST_TENANT_CONTEXT
FOREIGN = TenantContext(tenant_id=TenantId("tenant-foreign"))

# Every read that resolves a portfolio before a route serves data from it.
# Everything these surfaces publish is reached through one of them, which is why
# the predicate belongs here rather than in each of the twenty-one routes.
PORTFOLIO_RESOLVING_READS = (
    "get_portfolio_by_id",
    "list_portfolios",
    "portfolio_exists",
    "ensure_portfolio_exists",
    "get_portfolio_currency",
)


class _FakeResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


def _repo_with(rows: list[object]) -> tuple[ReportingRepository, AsyncMock]:
    db = AsyncMock(spec=AsyncSession)
    db.execute.return_value = _FakeResult(rows)
    return ReportingRepository(db), db


def _compiled(db: AsyncMock) -> str:
    statement = db.execute.await_args.args[0]
    return str(statement.compile(compile_kwargs={"literal_binds": True}))


@pytest.mark.asyncio
async def test_reporting_detail_read_carries_the_tenant_predicate() -> None:
    repo, db = _repo_with([SimpleNamespace(portfolio_id="PB_SG_GLOBAL_BAL_001")])

    await repo.get_portfolio_by_id("PB_SG_GLOBAL_BAL_001", tenant_id=TENANT.tenant_id)

    assert "portfolios.tenant_id = 'tenant-test'" in _compiled(db)


@pytest.mark.asyncio
async def test_a_foreign_tenant_selects_no_row_rather_than_a_narrowed_one() -> None:
    """The predicate is in the query, so the database returns nothing.

    Filtering after the read would be a different control: the row would have
    been fetched, and any logging, caching or metric on that path would have
    observed a portfolio the caller may not know exists.
    """
    repo, db = _repo_with([])

    result = await repo.get_portfolio_by_id("PB_SG_GLOBAL_BAL_001", tenant_id=FOREIGN.tenant_id)

    assert result is None
    assert "portfolios.tenant_id = 'tenant-foreign'" in _compiled(db)


@pytest.mark.asyncio
async def test_the_tenant_predicate_is_required_not_defaulted() -> None:
    """A default would silently preserve the unscoped behaviour.

    Every call site had to be updated to compile, which is how the liquidity
    ladder -- a caller in a different module reading the same repository -- was
    found. A default argument would have left it serving foreign portfolios with
    nothing to indicate it.
    """
    repo, _ = _repo_with([])

    with pytest.raises(TypeError):
        await repo.get_portfolio_by_id("PB_SG_GLOBAL_BAL_001")  # type: ignore[call-arg]

    with pytest.raises(TypeError):
        await repo.list_portfolios(portfolio_id="PB_SG_GLOBAL_BAL_001")  # type: ignore[call-arg]


def _portfolio_resolving_calls_without_a_tenant() -> list[str]:
    """Calls to the two portfolio-resolving reads that pass no tenant.

    An invariant rather than a list of known call sites: a route added later
    that resolves a portfolio without a tenant is the regression this tranche
    exists to prevent, and no enumeration written today would mention it.
    """
    offenders: list[str] = []
    for path in QUERY_SERVICE_APP.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in PORTFOLIO_RESOLVING_READS:
                continue
            if any(keyword.arg in ("tenant_id", "tenant_context") for keyword in node.keywords):
                continue
            offenders.append(f"{path.name}:{node.lineno} {node.func.attr}")
    return sorted(offenders)


def test_no_portfolio_resolving_read_omits_the_tenant() -> None:
    assert _portfolio_resolving_calls_without_a_tenant() == []


def test_the_invariant_scan_actually_reaches_the_call_sites() -> None:
    """Guards the invariant against passing because it found nothing at all.

    A scan matching zero calls reports zero offenders, and no coverage is the
    same green as full coverage.
    """
    found = 0
    for path in QUERY_SERVICE_APP.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in PORTFOLIO_RESOLVING_READS
            ):
                found += 1

    assert found >= 3


def test_every_reporting_route_passes_the_admitted_tenant() -> None:
    """The routes must take authority from request state, never from a body.

    A body-supplied tenant is caller-asserted, which is the shape that let an
    arbitrary `X-Tenant-Id` be recorded as evidence elsewhere in this service.
    """
    source = (QUERY_SERVICE_APP / "routers" / "reporting.py").read_text(encoding="utf-8")
    handlers = [
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.AsyncFunctionDef) and node.name.startswith("query_")
    ]

    assert len(handlers) == 4
    for handler in handlers:
        body = ast.get_source_segment(source, handler) or ""
        assert "tenant_context=http_request.state.tenant_context" in body, handler.name


# --- the shared portfolio-existence gate (#798 tranche C) ---------------------


@pytest.mark.asyncio
async def test_the_shared_existence_read_carries_the_tenant_predicate() -> None:
    """Eight repositories delegate here, so the predicate exists once.

    Each previously carried its own copy of the statement -- identical apart
    from a local variable name and one missing LIMIT -- and none of the eight
    filtered by tenant. A per-repository fix would have had to be got right
    eight times and kept right afterwards.
    """
    repo, db = _repo_with([SimpleNamespace(portfolio_id="PB_SG_GLOBAL_BAL_001")])

    await portfolio_exists_for_tenant(db, "PB_SG_GLOBAL_BAL_001", tenant_id=TENANT.tenant_id)

    assert "portfolios.tenant_id = 'tenant-test'" in _compiled(db)
    assert repo is not None


def test_the_existence_statement_is_not_duplicated_across_repositories() -> None:
    """The duplication was part of the defect, so it is asserted gone.

    If a repository grows its own copy again, the tenant predicate becomes
    something eight files have to agree about rather than one.
    """
    repositories = QUERY_SERVICE_APP / "repositories"
    offenders = [
        path.name
        for path in repositories.glob("*_repository.py")
        if "select(Portfolio.portfolio_id).where(Portfolio.portfolio_id == portfolio_id)"
        in path.read_text(encoding="utf-8").replace("\n", " ").replace("  ", " ")
    ]

    assert offenders == []


@pytest.mark.asyncio
async def test_a_foreign_tenant_cannot_learn_a_portfolio_exists() -> None:
    """The gate must not become an enumeration oracle.

    A caller that is refused for a portfolio it does not own must not be able to
    tell that refusal apart from one for an identifier that was never real.
    """
    absent_repo, absent_db = _repo_with([])

    foreign = await portfolio_exists_for_tenant(
        absent_db, "PB_SG_GLOBAL_BAL_001", tenant_id=FOREIGN.tenant_id
    )

    assert foreign is False
    assert "portfolios.tenant_id = 'tenant-foreign'" in _compiled(absent_db)
    assert absent_repo is not None
