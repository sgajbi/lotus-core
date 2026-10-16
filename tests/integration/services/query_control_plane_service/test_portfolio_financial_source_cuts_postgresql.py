"""Prepared PostgreSQL retained-read proof. Source only until separately admitted execution."""

import pytest
from portfolio_common.domain.portfolio_financial_source_cuts import InputRole
from portfolio_common.portfolio_financial_source_cut_models import FinancialSourceCutRow
from sqlalchemy import select

from src.services.query_control_plane_service.app.contracts.portfolio_financial_source_cuts import (
    FinancialSourceCutQuery,
    HistoricalRegistryQuery,
)
from src.services.query_control_plane_service.app.infrastructure import (
    portfolio_financial_source_cuts as retained,
)
from tests.integration.services.ingestion_service import (
    test_portfolio_financial_source_cuts_postgresql as owning,
)
from tests.unit.services.query_control_plane_service.infrastructure import (
    test_portfolio_financial_source_cuts as fixtures,
)

pytestmark = [pytest.mark.integration_db, pytest.mark.db_direct, pytest.mark.lifecycle]
observation_schema = owning.observation_schema
observation_lease = owning.observation_lease
neutral_schema = owning.neutral_schema
neutral_lease = owning.neutral_lease


@pytest.mark.asyncio
async def test_postgresql_tenant_fence_never_substitutes_a_complete_empty_manifest(
    async_db_session,
):
    """Requires admitted owning DB fixture and migration; never qualify this from compilation."""
    query, row, _, _ = fixtures.persisted_registry()
    assert async_db_session.bind.dialect.name == "postgresql"
    existing = await async_db_session.scalar(
        select(FinancialSourceCutRow).where(
            FinancialSourceCutRow.tenant_id == "synthetic-neutral-read-absent-tenant",
            FinancialSourceCutRow.source_cut_id == query.source_cut_id,
        )
    )
    assert existing is None
    with pytest.raises(LookupError):
        await retained.SqlAlchemyPortfolioFinancialSourceCutReader(async_db_session).cut(
            "synthetic-neutral-read-absent-tenant", row.product_name, query
        )


def native_query(request, tenant, *, portfolio=None):
    values = dict(
        source_system=request.source_system,
        registry_scope_id=request.registry_scope_id,
        source_cut_id=request.source_cut_id,
        revision=request.revision,
        content_hash=request.to_domain(tenant).content_hash,
        page=dict(page_size=10, page_token=None),
        view="MEMBERS" if portfolio is None else "INPUTS",
    )
    return (
        HistoricalRegistryQuery(**values)
        if portfolio is None
        else FinancialSourceCutQuery(**values, portfolio_id=portfolio)
    )


@pytest.mark.asyncio
async def test_populated_native_reader_keeps_selected_graph_and_tenant_fence(
    neutral_lease,
):
    lease = neutral_lease
    registry, financial, job, _ = await owning.populated_financial_case(lease, two_portfolios=True)
    await owning.drive_work(lease, owning.SyntheticCapturePort())
    registry_query = native_query(registry, lease.tenant)
    query = native_query(financial, lease.tenant, portfolio=lease.portfolio)
    async with lease.sessions() as session:
        assert session.bind.dialect.name == "postgresql"
        reader = retained.SqlAlchemyPortfolioFinancialSourceCutReader(session)
        registry_cut = await reader.cut(lease.tenant, "PortfolioHistoricalRegistry", registry_query)
        assert registry_cut.header.manifest.supplied_count == 2
        members = [member async for member in reader.members(lease.tenant, registry_query)]
        assert len(members) == 2
        assert {member.member.core_portfolio_id for member in members} == {
            lease.portfolio,
            lease.portfolio + "-second",
        }
        cut = await reader.cut(lease.tenant, "PortfolioFinancialSourceCut", query)
        assert (
            cut.header.receipt_job_id == job.job_id and cut.compatibility_posture == "UNAVAILABLE"
        )
        selected = await reader.selected_input(lease.tenant, query, cut)
        assert selected.graph.portfolio_id == lease.portfolio
        assert tuple(selection.role for selection in selected.graph.selections) == tuple(InputRole)
        assert selected.graph_content_hash == selected.graph.content_hash
        assert selected.graph.registry_root == registry.to_domain(lease.tenant).content_hash
        with pytest.raises(LookupError, match="exact retained cut absent"):
            await reader.cut("synthetic-other-tenant", "PortfolioFinancialSourceCut", query)
        absent = query.model_copy(update={"portfolio_id": "synthetic-absent-portfolio"})
        with pytest.raises(LookupError, match="selected retained financial input absent"):
            await reader.selected_input(lease.tenant, absent, cut)
        substituted = query.model_copy(update={"content_hash": "b" * 64})
        with pytest.raises(ValueError, match="retained raw and typed manifest mismatch"):
            await reader.cut(lease.tenant, "PortfolioFinancialSourceCut", substituted)


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["pending", "failed"])
async def test_native_reader_refuses_retained_but_uncompleted_or_rejected_financial_custody(
    neutral_lease,
    terminal,
):
    lease = neutral_lease
    _, financial, _, _ = await owning.populated_financial_case(
        lease, mappings=[None] if terminal == "failed" else None
    )
    if terminal == "failed":
        await owning.drive_work(lease, owning.ForbiddenSourceClient())
    query = native_query(financial, lease.tenant, portfolio=lease.portfolio)
    before = await owning.native_state(lease)
    async with lease.sessions() as session:
        with pytest.raises(
            ValueError, match="native retained terminal custody receipt unavailable"
        ):
            await retained.SqlAlchemyPortfolioFinancialSourceCutReader(session).cut(
                lease.tenant, "PortfolioFinancialSourceCut", query
            )
    assert await owning.native_state(lease) == before  # Reads cannot earn or rewrite completion.
