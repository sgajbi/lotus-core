"""Attached-receipt protocol and correction ordering; mocks do not qualify PostgreSQL."""

import json
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from portfolio_common.database_models import IngestionJob
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.portfolio_financial_source_cuts import ordered_content_root
from portfolio_common.domain.portfolio_source_observations import ObservationConflict
from portfolio_common.portfolio_financial_source_cut_admission import (
    FinancialInput,
    RegistryMemberInput,
)
from portfolio_common.portfolio_financial_source_cut_models import (
    FinancialSourceChunkRow,
    FinancialSourceCutRow,
    FinancialSourceCutWorkRow,
    FinancialSourceHeadRow,
    FinancialSourceInputRow,
    HistoricalRegistryMemberRow,
)
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.exc import IntegrityError

from src.services.ingestion_service.app.DTOs.portfolio_financial_source_cut_dto import (
    FinancialChunkInput,
    RegistryChunkInput,
    RegistrySealInput,
)
from src.services.ingestion_service.app.infrastructure import (
    portfolio_financial_source_cut_stager as module,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]
PortfolioFinancialSourceCutStager = module.PortfolioFinancialSourceCutStager
command_scope = module.command_scope
flush_unique_source_rows = module.flush_unique_source_rows
H = "a" * 64


def stager(*, corrected=False):
    stamp = datetime(2026, 10, 16, tzinfo=UTC)
    request = RegistrySealInput(
        source_system="producer",
        registry_scope_id="scope",
        source_cut_id="cut",
        revision=2 if corrected else 1,
        definition_version="v1",
        coverage_from=date(2025, 1, 1),
        coverage_to=date(2025, 1, 31),
        calendar="SG",
        observed_at=stamp,
        generated_at=stamp,
        predecessor_hash=H if corrected else None,
        expected_head_hash=H if corrected else None,
        expected_population={
            "reference": "independent",
            "definition_version": "v1",
            "count": 0,
            "content_hash": H,
        },
        declared_coverage="COMPLETE",
        supplied_count=0,
        members_root=ordered_content_root("PortfolioHistoricalRegistryMembers:v1", [])[1],
        chunk_count=0,
        chunks_root=ordered_content_root("NeutralSourceChunks:v1", [])[1],
    )
    return PortfolioFinancialSourceCutStager(
        request,
        "tenant",
        request.model_dump_json().encode(),
        stamp,
        "/ingest/portfolio-historical-registry-cuts",
        "portfolio_historical_registry",
    )


async def test_detached_native_receipt_cannot_invoke_creation_effect_or_sql():
    value = stager()
    session = SimpleNamespace(
        in_transaction=lambda: True, sync_session=object(), execute=AsyncMock(), scalar=AsyncMock()
    )
    receipt = IngestionJob(
        job_id="receipt",
        tenant_id="tenant",
        endpoint=value.endpoint,
        entity_type=value.entity_type,
        accepted_count=1,
        status="accepted",
    )
    with pytest.raises(ValueError, match="attached native receipt"):
        await value.stage(session, receipt)
    session.execute.assert_not_awaited()
    session.scalar.assert_not_awaited()


async def test_original_receipt_lookup_uses_exact_tenant_scope_and_raw_typed_identity():
    value = stager()
    import hashlib

    record = FinancialSourceCutRow(
        content_hash=value.request.to_domain("tenant").content_hash,
        raw_hash=hashlib.sha256(value.raw_bytes).hexdigest(),
        receipt_job_id="original",
    )
    session = SimpleNamespace(scalar=AsyncMock(return_value=record))

    @asynccontextmanager
    async def sessions():
        yield session

    assert await value.original_receipt(sessions) == "original"
    parameters = session.scalar.call_args.args[0].compile(dialect=dialect()).params
    assert {"tenant", "PortfolioHistoricalRegistry", "producer", "scope", "cut", 1} <= set(
        parameters.values()
    )
    record.raw_hash = "b" * 64
    with pytest.raises(ObservationConflict):
        await value.original_receipt(sessions)


@pytest.mark.parametrize("predecessor_status", ["PENDING", "CLAIMED", "FAILED", "COMPLETED"])
async def test_pending_predecessor_cannot_be_overtaken_but_terminal_predecessor_can_be_corrected(
    predecessor_status,
):
    value = stager(corrected=True)
    values = command_scope(value.request, "tenant")
    head = FinancialSourceHeadRow(**(values | {"revision": 1}), content_hash=H)
    counts = MagicMock()
    counts.one.return_value = (0, 0, None, None)
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[None, head, predecessor_status]),
        execute=AsyncMock(return_value=counts),
        add=Mock(),
        flush=AsyncMock(),
    )
    receipt = SimpleNamespace(job_id="new-original-receipt")
    if predecessor_status in {"PENDING", "CLAIMED"}:
        with pytest.raises(ObservationConflict, match="PREDECESSOR_CUSTODY_PENDING"):
            await value._seal(session, receipt, values)
        session.add.assert_not_called()
        assert head.revision == 1
    else:
        await value._seal(session, receipt, values)
        assert head.revision == 2
        work = next(
            call.args[0]
            for call in session.add.call_args_list
            if isinstance(call.args[0], FinancialSourceCutWorkRow)
        )
        assert work.receipt_job_id == receipt.job_id and work.partition_index == 0
        assert work.checkpoint == {"stage": "VERIFY_CHUNKS", "verified_rows": 0}


@pytest.mark.parametrize(
    "constraint,expected_conflict",
    [
        ("portfolio_historical_registry_members_pkey", True),
        ("portfolio_financial_source_cut_inputs_pkey", True),
        ("unrelated_owner_constraint", False),
    ],
)
async def test_only_known_cross_chunk_identity_duplicates_become_source_conflicts(
    constraint, expected_conflict
):
    driver = Exception("unit driver")
    driver.constraint_name = constraint
    original = Exception("unit adapter")
    original.sqlstate = "23505"
    original.__cause__ = driver
    error = IntegrityError("unit statement", {}, original)
    session = SimpleNamespace(flush=AsyncMock(side_effect=error))
    with pytest.raises(ObservationConflict if expected_conflict else IntegrityError):
        await flush_unique_source_rows(session)


async def test_valid_unique_source_rows_flush_without_rewriting_failure_policy():
    session = SimpleNamespace(flush=AsyncMock())
    await flush_unique_source_rows(session)
    session.flush.assert_awaited_once()


async def test_chunk_receipt_records_actual_database_completion_separately_from_first_ingress(
    monkeypatch,
):
    stamp = datetime(2026, 10, 16, tzinfo=UTC)
    completed = stamp + timedelta(seconds=2)
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
    value = PortfolioFinancialSourceCutStager(
        request,
        "tenant",
        request.model_dump_json().encode(),
        stamp,
        "/ingest/portfolio-historical-registry-chunks",
        "portfolio_historical_registry_chunk",
    )
    session = SimpleNamespace(
        sync_session=object(),
        in_transaction=lambda: True,
        execute=AsyncMock(),
        scalar=AsyncMock(return_value=completed),
        flush=AsyncMock(),
    )
    receipt = IngestionJob(
        job_id="receipt",
        tenant_id="tenant",
        endpoint=value.endpoint,
        entity_type=value.entity_type,
        accepted_count=0,
        status="accepted",
    )
    monkeypatch.setattr(
        module,
        "inspect",
        lambda row: SimpleNamespace(persistent=True, session=session.sync_session),
    )
    monkeypatch.setattr(PortfolioFinancialSourceCutStager, "_chunk", AsyncMock())
    await value.stage(session, receipt)
    assert receipt.status == "completed" and receipt.completed_at == completed
    assert receipt.completed_at > value.received_at
    assert "clock_timestamp" in str(session.scalar.call_args.args[0])


def populated_registry_chunk(*, duplicate=False):
    member = dict(
        source_member_id="member",
        provider_namespace="provider",
        core_portfolio_id="portfolio",
        member_revision=1,
        declarations=[
            dict(
                effective_from="2025-01-01",
                effective_to=None,
                definition_version="v1",
                provenance_reference="issued",
                currency="USD",
                discretionary=None,
                included=False,
            )
        ],
    )
    row = RegistryMemberInput.model_validate_json(json.dumps(member))
    members = (row, row) if duplicate else (row,)
    request = RegistryChunkInput(
        source_system="producer",
        registry_scope_id="scope",
        source_cut_id="cut",
        revision=1,
        chunk_index=0,
        members=members,
        typed_content_hash=canonical_content_hash(
            {
                "contract": "PortfolioHistoricalRegistryChunk:v1",
                "members": [item.to_domain().content_hash for item in members],
            }
        ),
    )
    return replace(stager(), request=request, raw_bytes=request.model_dump_json().encode())


async def test_actual_chunk_admits_owned_member_and_preserves_original_declaration_and_bytes():
    value = populated_registry_chunk()
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[None, None, "portfolio"]), add=Mock(), flush=AsyncMock()
    )
    await value._chunk(
        session, SimpleNamespace(job_id="receipt"), command_scope(value.request, "tenant")
    )
    chunk, member = [call.args[0] for call in session.add.call_args_list]
    assert isinstance(chunk, FinancialSourceChunkRow)
    assert chunk.raw_bytes == value.raw_bytes and chunk.row_count == 1
    assert (
        chunk.receipt_job_id == "receipt" and chunk.typed_hash == value.request.typed_content_hash
    )
    assert isinstance(member, HistoricalRegistryMemberRow)
    assert member.tenant_id == "tenant" and member.core_portfolio_id == "portfolio"
    assert member.declaration == value.request.members[0].model_dump(mode="json")
    assert member.content_hash == value.request.members[0].to_domain().content_hash
    ownership = session.scalar.call_args.args[0].compile(dialect=dialect()).params
    assert set(ownership.values()) == {"tenant", "portfolio"}


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("exact_replay", "EXISTING_RECEIPT_REQUIRED"),
        ("raw_replay", "DIVERGENT_REPLAY"),
        ("typed_replay", "DIVERGENT_REPLAY"),
        ("sealed", "ALREADY_SEALED"),
        ("foreign", "PORTFOLIO_NOT_OWNED"),
        ("duplicate", "ORDER_OR_DUPLICATE"),
    ],
)
async def test_actual_chunk_refuses_replay_sealed_foreign_and_duplicate_members(mutation, code):
    import hashlib

    value = populated_registry_chunk(duplicate=mutation == "duplicate")
    existing = SimpleNamespace(
        typed_hash=value.request.typed_content_hash,
        raw_hash=hashlib.sha256(value.raw_bytes).hexdigest(),
    )
    if mutation == "raw_replay":
        existing.raw_hash = "b" * 64
    elif mutation == "typed_replay":
        existing.typed_hash = "b" * 64
    responses = (
        [existing]
        if "replay" in mutation
        else [None, object()]
        if mutation == "sealed"
        else [None, None, None]
        if mutation == "foreign"
        else [None, None, "portfolio"]
    )
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=responses), add=Mock(), flush=AsyncMock()
    )
    with pytest.raises(ObservationConflict, match=code):
        await value._chunk(
            session, SimpleNamespace(job_id="receipt"), command_scope(value.request, "tenant")
        )
    rows = [call.args[0] for call in session.add.call_args_list]
    assert not any(isinstance(row, FinancialSourceCutWorkRow) for row in rows)
    if "replay" in mutation or mutation == "sealed":
        session.add.assert_not_called()
        session.flush.assert_not_awaited()
    else:
        # Pending session rows are not persisted proof; native tests own transaction rollback.
        assert sum(isinstance(row, HistoricalRegistryMemberRow) for row in rows) == int(
            mutation == "duplicate"
        )


async def test_attached_receipt_wrong_count_refuses_before_sql_or_materialization(monkeypatch):
    value = populated_registry_chunk()
    session = SimpleNamespace(
        sync_session=object(),
        in_transaction=lambda: True,
        execute=AsyncMock(),
        scalar=AsyncMock(),
        add=Mock(),
        flush=AsyncMock(),
    )
    receipt = IngestionJob(
        job_id="receipt",
        tenant_id="tenant",
        endpoint=value.endpoint,
        entity_type=value.entity_type,
        accepted_count=0,
        status="accepted",
    )
    monkeypatch.setattr(
        module,
        "inspect",
        lambda row: SimpleNamespace(persistent=True, session=session.sync_session),
    )
    with pytest.raises(ValueError, match="count does not match"):
        await value.stage(session, receipt)
    session.execute.assert_not_awaited()
    session.scalar.assert_not_awaited()
    session.add.assert_not_called()
    assert receipt.status == "accepted"


def populated_financial_chunk():
    valuation = dict(
        kind="VALUATION",
        as_of_date="2025-01-31",
        from_date="2024-12-31",
        to_date="2025-01-31",
        reporting_currency="USD",
        consumer_system="lotus-manage",
        export_job_id=None,
        export_content_hash=None,
        refresh_of_job_id=None,
    )
    observation = dict(
        as_of_date="2025-01-31",
        producer_id="producer",
        source_record_id="record",
        observation_id=H,
        content_hash=H,
        source_cut_id="native",
        source_version=1,
    )
    flow = dict(
        kind="FLOWS",
        source_system="producer",
        source_cut_id="flow",
        cut_revision=1,
        manifest_hash=H,
        from_date="2025-01-01",
        to_date="2025-01-31",
        currency="USD",
    )
    sources = [
        ("PRIOR_ASSETS", "PortfolioTimeseriesInput", valuation),
        ("MONTH_END_ASSETS", "PortfolioTimeseriesInput", valuation),
        ("CASH", "PortfolioFinancialSourceObservations", observation | {"kind": "CASH"}),
        ("READINESS", "PortfolioFinancialSourceObservations", observation | {"kind": "READINESS"}),
        ("FLOWS", "PortfolioFinancialFlowObservations", flow),
    ]
    record = FinancialInput.model_validate_json(
        json.dumps(
            dict(
                portfolio_id="portfolio",
                currency="USD",
                prior_date="2024-12-31",
                month_end_date="2025-01-31",
                registry_root=H,
                member_revision=1,
                settled_unencumbered=None,
                compatibility=None,
                selections=[
                    dict(
                        role=role,
                        product_name=product,
                        product_version="v1",
                        selector=selector,
                        selector_hash=canonical_content_hash(selector),
                        content_hash=H,
                        receipt_job_id="native-receipt",
                        source_revision="1",
                    )
                    for role, product, selector in sources
                ],
            )
        )
    )
    request = FinancialChunkInput(
        source_system="producer",
        registry_scope_id="scope",
        source_cut_id="cut",
        revision=1,
        chunk_index=0,
        selections=(record,),
        typed_content_hash=canonical_content_hash(
            {
                "contract": "PortfolioFinancialSourceCutChunk:v1",
                "selections": [record.model_dump(mode="json")],
            }
        ),
    )
    return replace(stager(), request=request, raw_bytes=request.model_dump_json().encode())


async def test_actual_financial_chunk_materializes_owned_selection_without_filling_unknowns():
    value = populated_financial_chunk()
    session = SimpleNamespace(
        scalar=AsyncMock(side_effect=[None, None, "portfolio"]), add=Mock(), flush=AsyncMock()
    )
    await value._chunk(
        session, SimpleNamespace(job_id="receipt"), command_scope(value.request, "tenant")
    )
    chunk, selection = [call.args[0] for call in session.add.call_args_list]
    assert chunk.product_name == "PortfolioFinancialSourceCut" and chunk.row_count == 1
    assert isinstance(selection, FinancialSourceInputRow)
    assert selection.tenant_id == "tenant" and selection.portfolio_id == "portfolio"
    assert selection.content_hash == module.financial_input_hash(value.request.selections[0])
    assert selection.declaration == value.request.selections[0].model_dump(mode="json")
    assert selection.declaration["compatibility"] is None
    assert selection.declaration["settled_unencumbered"] is None
