"""Neutral admission precedes any receipt lookup/write; original replay remains source custody."""

from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.tenant import TenantContext, TenantId
from portfolio_common.portfolio_financial_source_cut_admission import RegistrySourceGrant

from src.services.ingestion_service.app.DTOs.portfolio_financial_source_cut_dto import (
    RegistryChunkInput,
)
from src.services.ingestion_service.app.services import (
    portfolio_financial_source_cut_commands as module,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def submission():
    request = RegistryChunkInput(
        source_system="producer",
        registry_scope_id="scope",
        source_cut_id="cut",
        revision=1,
        chunk_index=0,
        members=(),
        typed_content_hash=canonical_content_hash(
            {"contract": "PortfolioHistoricalRegistryChunk:v1", "members": []}
        ),
    )
    return module.NeutralSourceSubmission(
        TenantContext(TenantId("tenant"), service_identity="producer", identity_verified=True),
        request,
        "key",
        request.model_dump_json().encode(),
        datetime(2026, 10, 16, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    "case", ["default", "tenant", "producer", "scope", "product", "unverified", "actor"]
)
async def test_wrong_or_missing_scope_has_no_receipt_or_rate_effect(monkeypatch, case):
    value = submission()
    grant = RegistrySourceGrant(
        "tenant", "producer", "scope", frozenset({"PortfolioHistoricalRegistry"})
    )
    if case == "tenant":
        grant = replace(grant, tenant_id="foreign")
    elif case == "producer":
        grant = replace(grant, source_system="foreign")
    elif case == "scope":
        grant = replace(grant, registry_scope_id="foreign")
    elif case == "product":
        grant = replace(grant, products=frozenset({"PortfolioFinancialSourceCut"}))
    elif case == "unverified":
        value = replace(
            value, tenant_context=replace(value.tenant_context, identity_verified=False)
        )
    elif case == "actor":
        value = replace(
            value, tenant_context=replace(value.tenant_context, service_identity="foreign")
        )
    factory, sessions, rate = Mock(), Mock(), Mock()
    monkeypatch.setattr(module, "enforce_ingestion_write_rate_limit", rate)
    commands = module.PortfolioFinancialSourceCutCommands(
        () if case == "default" else (grant,), factory, sessions
    )
    with pytest.raises(PermissionError):
        await commands.submit(value)
    factory.assert_not_called()
    sessions.assert_not_called()
    rate.assert_not_called()


async def test_exact_replay_returns_original_native_receipt_without_write_or_rate(monkeypatch):
    original = SimpleNamespace(job_id="original", status="completed")
    service = SimpleNamespace(
        get_job=AsyncMock(return_value=original),
        assert_ingestion_writable=AsyncMock(),
        create_or_get_job=AsyncMock(),
    )
    lookup = AsyncMock(return_value="original")
    monkeypatch.setattr(module.PortfolioFinancialSourceCutStager, "original_receipt", lookup)
    rate = Mock()
    monkeypatch.setattr(module, "enforce_ingestion_write_rate_limit", rate)
    commands = module.PortfolioFinancialSourceCutCommands(
        (
            RegistrySourceGrant(
                "tenant", "producer", "scope", frozenset({"PortfolioHistoricalRegistry"})
            ),
        ),
        lambda stager: service,
        Mock(),
    )
    assert await commands.submit(submission()) is original
    service.get_job.assert_awaited_once_with("original", tenant_id="tenant")
    service.create_or_get_job.assert_not_awaited()
    service.assert_ingestion_writable.assert_not_awaited()
    rate.assert_not_called()


async def test_actual_dependency_binds_read_context_manager_separately_from_receipt_generator(
    monkeypatch,
):
    from src.services.ingestion_service.app import dependencies

    session = SimpleNamespace(scalar=AsyncMock(return_value=None))

    @asynccontextmanager
    async def read_sessions():
        yield session

    monkeypatch.setattr(dependencies, "AsyncSessionLocal", read_sessions)
    monkeypatch.setenv(
        "LOTUS_PORTFOLIO_REGISTRY_SOURCE_GRANTS_JSON",
        '[{"tenant_id":"tenant","source_system":"producer","registry_scope_id":"scope","products":["PortfolioHistoricalRegistry"]}]',
    )
    commands = dependencies.get_portfolio_financial_source_cut_commands()
    assert commands.sessions is read_sessions
    service = SimpleNamespace(
        assert_ingestion_writable=AsyncMock(),
        create_or_get_job=AsyncMock(
            return_value=SimpleNamespace(job=SimpleNamespace(job_id="original"))
        ),
    )
    commands.service_factory = lambda stager: service
    monkeypatch.setattr(module, "enforce_ingestion_write_rate_limit", Mock())
    assert (await commands.submit(submission())).job_id == "original"
    session.scalar.assert_awaited_once()
    service.create_or_get_job.assert_awaited_once()
