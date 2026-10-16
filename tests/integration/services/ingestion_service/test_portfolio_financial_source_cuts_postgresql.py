"""Prepared owned PostgreSQL custody proof; execution requires Root's admitted dependency."""

import asyncio
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from portfolio_common.database_models import IngestionJob, OutboxEvent, Portfolio
from portfolio_common.domain.calculation_lineage import canonical_content_hash
from portfolio_common.domain.portfolio_financial_source_cuts import InputRole, ordered_content_root
from portfolio_common.domain.portfolio_source_observations import ObservationConflict
from portfolio_common.portfolio_financial_source_cut_admission import (
    FinancialInput,
    RegistryMemberInput,
)
from portfolio_common.portfolio_financial_source_cut_models import (
    FinancialSourceCaptureLinkRow,
    FinancialSourceCaptureRow,
    FinancialSourceCaptureSegmentRow,
    FinancialSourceChunkRow,
    FinancialSourceCutRow,
    FinancialSourceCutWorkRow,
    FinancialSourceHeadRow,
    FinancialSourceInputRow,
    HistoricalRegistryMemberRow,
)
from sqlalchemy import func, select, update

from src.services.ingestion_service.app.application.reference_data_ingestion_registry import (
    REFERENCE_DATA_INGESTION_REGISTRY,
)
from src.services.ingestion_service.app.DTOs.portfolio_financial_source_cut_dto import (
    FinancialChunkInput,
    FinancialSealInput,
    RegistryChunkInput,
    RegistrySealInput,
)
from src.services.ingestion_service.app.infrastructure import (
    portfolio_financial_source_cut_stager as source_stager,
)
from src.services.ingestion_service.app.services.ingestion_job_lifecycle import (
    create_or_get_job_result,
)
from src.services.persistence_service.app.application.financial_source_cut_processing import (
    FinancialSourceCutProcessor,
)
from src.services.persistence_service.app.ports.financial_source_captures import (
    CapturedSourcePage,
    SourceCaptureBytes,
    SourceCaptureUnavailable,
)
from src.services.persistence_service.app.ports.financial_source_cut_work import (
    SourceCutProgress,
    SourceManifestRejected,
    StaleSourceCutClaim,
)
from src.services.persistence_service.app.repositories.financial_source_cut_work_repository import (
    FinancialSourceCutWorkRepository,
)
from tests.integration.services.ingestion_service import (
    test_portfolio_source_observation_admission_postgresql as native,
)
from tests.test_support.portfolio_source_test_schema import financial_source_cut_migration

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration_db,
    pytest.mark.db_direct,
    pytest.mark.lifecycle,
]
PortfolioFinancialSourceCutStager = source_stager.PortfolioFinancialSourceCutStager
observation_schema = native.observation_schema
observation_lease = native.observation_lease


@pytest.fixture
def neutral_schema(observation_schema):
    engine, authorization, schema, _ = observation_schema
    from sqlalchemy import text

    from tests.test_support.db_cleanup import require_database_cleanup_authorization

    require_database_cleanup_authorization(authorization, engine=engine)
    with engine.begin() as connection:
        # Reuse the exact governed owner namespace; never create/drop public data.
        connection.execute(text(f'SET LOCAL search_path TO "{schema}", pg_temp'))
        financial_source_cut_migration(connection)["upgrade"]()
        OutboxEvent.__table__.create(connection)
    return schema


@pytest_asyncio.fixture
async def neutral_lease(neutral_schema, observation_lease):
    assert observation_lease.schema == neutral_schema
    yield observation_lease


def registry_request(*, revision=1, predecessor=None):
    return RegistrySealInput(
        source_system="synthetic-source",
        registry_scope_id="registry",
        source_cut_id="cut",
        revision=revision,
        definition_version="v1",
        coverage_from=date(2025, 1, 1),
        coverage_to=date(2025, 1, 31),
        calendar="SG",
        observed_at=datetime(2026, 10, 16, tzinfo=UTC),
        generated_at=datetime(2026, 10, 16, tzinfo=UTC),
        predecessor_hash=predecessor,
        expected_head_hash=predecessor,
        expected_population={
            "reference": "independent",
            "definition_version": "v1",
            "count": 0,
            "content_hash": "a" * 64,
        },
        declared_coverage="COMPLETE",
        supplied_count=0,
        members_root=ordered_content_root("PortfolioHistoricalRegistryMembers:v1", [])[1],
        chunk_count=0,
        chunks_root=ordered_content_root("NeutralSourceChunks:v1", [])[1],
    )


async def stage_command(lease, request, *, raw_bytes=None, idempotency=None):
    product, chunk = source_stager.command_kind(request)
    key = (
        "portfolio_historical_registry"
        if product == "PortfolioHistoricalRegistry"
        else "portfolio_financial_source_cut"
    )
    command = REFERENCE_DATA_INGESTION_REGISTRY.require(key + ("_chunk" if chunk else ""))
    count = (
        len(request.members)
        if isinstance(request, RegistryChunkInput)
        else (len(request.selections) if isinstance(request, FinancialChunkInput) else 1)
    )
    stager = PortfolioFinancialSourceCutStager(
        request,
        lease.tenant,
        request.model_dump_json().encode() if raw_bytes is None else raw_bytes,
        datetime.now(UTC),
        command.endpoint,
        command.entity_type,
    )

    async def sessions():
        async with lease.sessions() as session:
            yield session

    result = await create_or_get_job_result(
        job_id=str(uuid4()),
        tenant_id=lease.tenant,
        endpoint=stager.endpoint,
        entity_type=stager.entity_type,
        accepted_count=count,
        idempotency_key=idempotency or str(uuid4()),
        correlation_id="synthetic-neutral-correlation",
        request_id="synthetic-neutral-request",
        trace_id="synthetic-neutral-trace",
        request_payload=request.model_dump(mode="json"),
        fingerprint_key_id="synthetic-key",
        fingerprint_hmac_secret="synthetic-test-secret",
        fingerprint_previous_keys={},
        session_factory=sessions,
        on_created=stager.stage,
    )
    return result.job, stager


async def stage_registry(lease, request):
    return await stage_command(lease, request)


def registry_commands(lease, mappings=None, *, page_size=1):
    mappings = [lease.portfolio] if mappings is None else mappings
    members, chunks = [], []
    address = dict(
        source_system="synthetic-source",
        registry_scope_id="registry",
        source_cut_id="cut",
        revision=1,
    )
    for index, portfolio in enumerate(mappings):
        member = dict(
            source_member_id=f"member-{index:04}",
            provider_namespace="synthetic-provider",
            core_portfolio_id=portfolio,
            member_revision=1,
            declarations=[
                dict(
                    effective_from="2025-01-01",
                    effective_to=None,
                    definition_version="v1",
                    provenance_reference="synthetic-declaration",
                    currency="USD",
                    discretionary=None,
                    included=True,
                )
            ],
        )
        typed = RegistryMemberInput.model_validate(member)
        members.append(typed)
    for index, first in enumerate(range(0, len(members), page_size)):
        page = tuple(members[first : first + page_size])
        chunks.append(
            RegistryChunkInput(
                **address,
                chunk_index=index,
                members=page,
                typed_content_hash=canonical_content_hash(
                    {
                        "contract": "PortfolioHistoricalRegistryChunk:v1",
                        "members": [member.to_domain().content_hash for member in page],
                    }
                ),
            )
        )
    body = registry_request().model_dump()
    body.update(
        supplied_count=len(members),
        chunk_count=len(chunks),
        expected_population=dict(
            reference="independent",
            definition_version="v1",
            count=len(members),
            content_hash="a" * 64,
        ),
        members_root=ordered_content_root(
            "PortfolioHistoricalRegistryMembers:v1", [m.to_domain().content_hash for m in members]
        )[1],
        chunks_root=ordered_content_root(
            "NeutralSourceChunks:v1", [chunk.typed_content_hash for chunk in chunks]
        )[1],
    )
    return chunks, RegistrySealInput.model_validate(body)


def selected_input(portfolio, registry_root):
    selections = []
    for role in InputRole:
        if role in (InputRole.PRIOR_ASSETS, InputRole.MONTH_END_ASSETS):
            product = "PortfolioTimeseriesInput"
            selector = dict(
                kind="VALUATION",
                as_of_date="2025-01-31",
                from_date="2024-12-31",
                to_date="2025-01-31",
                reporting_currency="USD",
                consumer_system="lotus-manage",
                export_job_id="synthetic-export-" + role.value,
                export_content_hash="a" * 64,
                refresh_of_job_id=None,
            )
        elif role is InputRole.FLOWS:
            product = "PortfolioFinancialFlowObservations"
            selector = dict(
                kind="FLOWS",
                source_system="synthetic-source",
                source_cut_id="native-flow",
                cut_revision=1,
                manifest_hash="a" * 64,
                from_date="2025-01-01",
                to_date="2025-01-31",
                currency="USD",
            )
        else:
            product = "PortfolioFinancialSourceObservations"
            selector = dict(
                kind=role.value,
                as_of_date="2025-01-31",
                producer_id="synthetic-source",
                source_record_id=role.value,
                observation_id="a" * 64,
                content_hash="a" * 64,
                source_cut_id="native-observation",
                source_version=1,
            )
        selections.append(
            dict(
                role=role.value,
                product_name=product,
                product_version="v1",
                selector=selector,
                selector_hash=canonical_content_hash(selector),
                content_hash="a" * 64,
                receipt_job_id="synthetic-receipt-" + role.value,
                source_revision="1",
            )
        )
    return FinancialInput.model_validate(
        dict(
            portfolio_id=portfolio,
            currency="USD",
            prior_date="2024-12-31",
            month_end_date="2025-01-31",
            registry_root=registry_root,
            member_revision=1,
            selections=selections,
            settled_unencumbered=None,
            compatibility=None,
        )
    )


def financial_commands(lease, registry, portfolios=None, *, revision=1, predecessor=None):
    portfolios = [lease.portfolio] if portfolios is None else portfolios
    inputs = [
        selected_input(portfolio, registry.to_domain(lease.tenant).content_hash)
        for portfolio in portfolios
    ]
    address = dict(
        source_system="synthetic-source",
        registry_scope_id="registry",
        source_cut_id="financial-cut",
        revision=revision,
    )
    chunks = [
        FinancialChunkInput(
            **address,
            chunk_index=index,
            selections=(record,),
            typed_content_hash=canonical_content_hash(
                {
                    "contract": "PortfolioFinancialSourceCutChunk:v1",
                    "selections": [record.model_dump(mode="json")],
                }
            ),
        )
        for index, record in enumerate(inputs)
    ]
    body = registry_request(revision=revision, predecessor=predecessor).header().model_dump()
    body.update(
        **address,
        selection_count=len(inputs),
        chunk_count=len(chunks),
        selections_root=ordered_content_root(
            "PortfolioFinancialSourceCutInputs:v1",
            [source_stager.financial_input_hash(record) for record in inputs],
        )[1],
        chunks_root=ordered_content_root(
            "NeutralSourceChunks:v1", [chunk.typed_content_hash for chunk in chunks]
        )[1],
    )
    return chunks, FinancialSealInput.model_validate(body)


async def stage_chunks_and_seal(lease, chunks, seal):
    for chunk in chunks:
        await stage_command(lease, chunk)
    return await stage_command(lease, seal)


async def add_portfolio(lease, portfolio, *, tenant=None):
    async with lease.sessions.begin() as session:
        existing = await session.scalar(
            select(Portfolio).where(
                Portfolio.tenant_id == lease.tenant, Portfolio.portfolio_id == lease.portfolio
            )
        )
        values = {
            column.name: getattr(existing, column.name)
            for column in Portfolio.__table__.columns
            if column.name != "id"
        }
        values.update(portfolio_id=portfolio, tenant_id=tenant or lease.tenant)
        session.add(Portfolio(**values))


class SyntheticCapturePort:
    """Controlled opaque acquisition-port bytes; never supplier, financial or bank proof."""

    def __init__(self, *, large=False):
        self.large = large
        self.requests = []

    async def close(self):
        pass  # No external transport is opened by this synthetic port.

    async def fetch(self, request):
        self.requests.append(request)
        valuation = request.role in (InputRole.PRIOR_ASSETS, InputRole.MONTH_END_ASSETS)
        raw = json.dumps(dict(synthetic=True, capture_id=request.capture_id)).encode()
        if self.large and request.role is InputRole.PRIOR_ASSETS and request.page_index == 0:
            raw += b" " * (1_048_576 + 37)

        async def chunks():
            for offset in range(0, len(raw), 524288):
                yield raw[offset : offset + 524288]

        owned = await SourceCaptureBytes.acquire(chunks())
        return CapturedSourcePage(
            request,
            owned,
            "synthetic-custody-port:v1",
            "application/json",
            request.expected_content_hash,
            "17" if valuation else None,
            "synthetic-scope",
            1,
            2 if valuation else 1,
            "next-page" if valuation and request.page_index == 0 else None,
            request.receipt_job_id,
            datetime.now(UTC),
            "v1",
            export_job_id="synthetic-export-" + request.role.value if valuation else None,
        )


async def native_state(lease):
    models = (
        IngestionJob,
        FinancialSourceChunkRow,
        HistoricalRegistryMemberRow,
        FinancialSourceInputRow,
        FinancialSourceCutRow,
        FinancialSourceHeadRow,
        FinancialSourceCutWorkRow,
        FinancialSourceCaptureRow,
        FinancialSourceCaptureSegmentRow,
        FinancialSourceCaptureLinkRow,
        OutboxEvent,
    )
    async with lease.sessions() as session:
        counts = {
            model.__tablename__: await session.scalar(select(func.count()).select_from(model))
            for model in models
        }
        jobs = [
            (row.job_id, row.status, row.completed_at)
            for row in (
                await session.scalars(select(IngestionJob).order_by(IngestionJob.job_id))
            ).all()
        ]
        work = [
            (row.work_id, row.status, row.lease_token, row.checkpoint)
            for row in (
                await session.scalars(
                    select(FinancialSourceCutWorkRow).order_by(FinancialSourceCutWorkRow.work_id)
                )
            ).all()
        ]
        return counts, jobs, work


async def make_pending_work_available(lease):
    async with lease.sessions.begin() as session:
        await session.execute(
            update(FinancialSourceCutWorkRow)
            .where(FinancialSourceCutWorkRow.status == "PENDING")
            .values(available_at=func.clock_timestamp())
        )


async def drive_work(lease, client):
    processor = FinancialSourceCutProcessor(
        FinancialSourceCutWorkRepository(lease.sessions), client
    )
    for _ in range(200):
        if await processor.step():
            continue
        async with lease.sessions() as session:
            pending = await session.scalar(
                select(func.count())
                .select_from(FinancialSourceCutWorkRow)
                .where(FinancialSourceCutWorkRow.status.in_(["PENDING", "CLAIMED"]))
            )
        if not pending:
            return
        # Advance only retry eligibility, not checkpoints or completion; avoid wall-clock sleeps.
        await make_pending_work_available(lease)
    raise AssertionError("bounded native work did not reach terminal custody")


async def populated_financial_case(lease, *, two_portfolios=False, mappings=None):
    portfolios = [lease.portfolio]
    if two_portfolios:
        portfolios.append(lease.portfolio + "-second")
        await add_portfolio(lease, portfolios[-1])
    registry_chunks, registry = registry_commands(
        lease, portfolios if mappings is None else mappings
    )
    await stage_chunks_and_seal(lease, registry_chunks, registry)
    await drive_work(lease, ForbiddenSourceClient())
    chunks, financial = financial_commands(lease, registry, portfolios)
    job, stager = await stage_chunks_and_seal(lease, chunks, financial)
    return registry, financial, job, stager


async def next_capture_claim(lease, repository):
    for _ in range(40):
        claim = await repository.claim()
        if claim is None:
            await make_pending_work_available(lease)
            continue
        request = await repository.next_capture(claim)
        if isinstance(request, SourceCutProgress):
            await repository.advance(claim, request)
        elif request is None:
            await repository.complete(claim)
        else:
            return claim, request
    raise AssertionError("no bounded capture claim available")


class ForbiddenSourceClient:
    async def fetch(self, request):
        raise AssertionError(
            "registry completion must not synthesize or refetch a financial source"
        )

    async def close(self):
        pass


async def finish_registry(lease):
    processor = FinancialSourceCutProcessor(
        FinancialSourceCutWorkRepository(lease.sessions), ForbiddenSourceClient()
    )
    for _ in range(3):
        assert await processor.step()
    assert await processor.step() is False


async def test_owned_postgresql_empty_registry_completes_job_work_and_one_outbox_atomically(
    neutral_lease,
):
    lease, request = neutral_lease, registry_request()
    original, stager = await stage_registry(lease, request)
    assert original.status == "accepted"
    await finish_registry(lease)
    async with lease.sessions() as session:
        job = await session.scalar(
            select(IngestionJob).where(
                IngestionJob.tenant_id == lease.tenant, IngestionJob.job_id == original.job_id
            )
        )
        record = await session.scalar(
            select(FinancialSourceCutRow).where(FinancialSourceCutRow.tenant_id == lease.tenant)
        )
        work = await session.scalar(
            select(FinancialSourceCutWorkRow).where(
                FinancialSourceCutWorkRow.tenant_id == lease.tenant
            )
        )
        events = (await session.scalars(select(OutboxEvent))).all()
        assert (
            job.status == "completed"
            and job.completed_at is not None
            and work.status == "COMPLETED"
        )
        assert (
            record.row_count == 0
            and record.content_hash == request.to_domain(lease.tenant).content_hash
        )
        assert len(events) == 1 and events[0].payload["receipt_job_id"] == original.job_id
        assert events[0].payload["qualification"] == "UNQUALIFIED"
        assert events[0].payload["population_verification"] == "UNVERIFIED"
    assert await stager.original_receipt(lease.sessions) == original.job_id


async def test_owned_postgresql_pending_correction_and_raw_divergence_refuse(
    neutral_lease,
):
    lease, request = neutral_lease, registry_request()
    original, stager = await stage_registry(lease, request)
    correction = registry_request(
        revision=2, predecessor=request.to_domain(lease.tenant).content_hash
    )
    with pytest.raises(ObservationConflict, match="PREDECESSOR_CUSTODY_PENDING"):
        await stage_registry(lease, correction)
    async with lease.sessions() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(IngestionJob)
                .where(IngestionJob.tenant_id == lease.tenant)
            )
            == 1
        )
    await finish_registry(lease)
    changed, _ = await stage_registry(lease, correction)
    assert changed.job_id != original.job_id
    from dataclasses import replace

    with pytest.raises(ObservationConflict):
        await replace(stager, raw_bytes=stager.raw_bytes + b" ").original_receipt(lease.sessions)


async def test_owned_postgresql_expired_worker_cannot_complete_or_emit_and_reclaim_changes_token(
    neutral_lease,
):
    lease = neutral_lease
    original, _ = await stage_registry(lease, registry_request())
    repository = FinancialSourceCutWorkRepository(lease.sessions)
    claim = await repository.claim()
    async with lease.sessions.begin() as session:
        await session.execute(
            update(FinancialSourceCutWorkRow)
            .where(
                FinancialSourceCutWorkRow.work_id == claim.work_id,
                FinancialSourceCutWorkRow.tenant_id == lease.tenant,
            )
            .values(lease_expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )
    with pytest.raises(StaleSourceCutClaim):
        await repository.complete(claim)
    recovered = await repository.claim()
    assert recovered.work_id == claim.work_id and recovered.lease_token != claim.lease_token
    async with lease.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 0
        job = await session.scalar(
            select(IngestionJob).where(
                IngestionJob.job_id == original.job_id, IngestionJob.tenant_id == lease.tenant
            )
        )
        assert job.status == "accepted" and job.completed_at is None


async def test_populated_registry_and_five_role_custody_persist_bounded_pages_and_terminal_facts(
    neutral_lease,
):
    lease = neutral_lease
    registry, financial, job, stager = await populated_financial_case(lease, two_portfolios=True)
    client = SyntheticCapturePort(large=True)
    await drive_work(lease, client)
    assert len(client.requests) == 14
    assert {request.role for request in client.requests} == set(InputRole)
    async with lease.sessions() as session:
        rows = (
            await session.scalars(
                select(FinancialSourceCutWorkRow).where(
                    FinancialSourceCutWorkRow.product_name == "PortfolioFinancialSourceCut"
                )
            )
        ).all()
        assert len(rows) == 3 and all(row.status == "COMPLETED" for row in rows)
        root = next(row for row in rows if row.partition_index == 0)
        assert root.checkpoint["stage"] == "READY" and root.checkpoint["spawned_chunks"] == 2
        assert all(
            row.checkpoint["completed_inputs"] == 1 for row in rows if row.partition_index > 0
        )
        assert await session.scalar(select(func.count()).select_from(FinancialSourceInputRow)) == 2
        assert (
            await session.scalar(select(func.count()).select_from(HistoricalRegistryMemberRow)) == 2
        )
        links = (await session.scalars(select(FinancialSourceCaptureLinkRow))).all()
        assert len(links) == 14 and {link.page_index for link in links} == {0, 1}
        assert (
            await session.scalar(select(func.count()).select_from(FinancialSourceCaptureRow)) == 14
        )
        assert (
            await session.scalar(select(func.count()).select_from(FinancialSourceCaptureSegmentRow))
            == 18
        )
        events = (await session.scalars(select(OutboxEvent))).all()
        assert len(events) == 2
        assert {event.payload["product_name"] for event in events} == {
            "PortfolioHistoricalRegistry",
            "PortfolioFinancialSourceCut",
        }
        assert all(event.payload["qualification"] == "UNQUALIFIED" for event in events)
        assert all(event.payload["population_verification"] == "UNVERIFIED" for event in events)
        completed = await session.scalar(
            select(IngestionJob).where(IngestionJob.job_id == job.job_id)
        )
        assert completed.status == "completed" and completed.completed_at is not None
        manifest = await session.scalar(
            select(FinancialSourceCutRow).where(
                FinancialSourceCutRow.product_name == "PortfolioFinancialSourceCut"
            )
        )
        assert manifest.content_hash == financial.to_domain(lease.tenant).content_hash
        assert registry.to_domain(lease.tenant).supplied_count == 2
    before = await native_state(lease)
    assert await stager.original_receipt(lease.sessions) == job.job_id
    await drive_work(lease, ForbiddenSourceClient())
    assert await native_state(lease) == before  # No duplicate job, capture, link or terminal fact.


async def test_correction_reuses_verified_capture_bytes_and_refuses_divergent_reacquisition(
    neutral_lease,
):
    lease = neutral_lease
    registry, financial, _, _ = await populated_financial_case(lease)
    await drive_work(lease, SyntheticCapturePort())
    chunks, correction = financial_commands(
        lease, registry, revision=2, predecessor=financial.to_domain(lease.tenant).content_hash
    )
    correction_job, _ = await stage_chunks_and_seal(lease, chunks, correction)
    repository = FinancialSourceCutWorkRepository(lease.sessions)
    claim, request = await next_capture_claim(lease, repository)
    page = await SyntheticCapturePort(large=True).fetch(request)
    before = await native_state(lease)
    try:
        with pytest.raises(SourceCaptureUnavailable, match="SOURCE_CAPTURE_DIVERGENT_REPLAY"):
            await repository.save_capture(claim, page)
    finally:
        page.capture_bytes.close()
    assert await native_state(lease) == before
    # Release the unchanged claim; actual processor must now use the immutable cache.
    await repository.defer(claim, "SOURCE_CAPTURE_UNAVAILABLE")
    await drive_work(lease, ForbiddenSourceClient())
    async with lease.sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(FinancialSourceCaptureRow)) == 7
        )
        assert (
            await session.scalar(select(func.count()).select_from(FinancialSourceCaptureLinkRow))
            == 14
        )
        job = await session.scalar(
            select(IngestionJob).where(IngestionJob.job_id == correction_job.job_id)
        )
        assert job.status == "completed"
        assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 3


@pytest.mark.parametrize("mapping", ["missing", "ambiguous", "wrong_root", "rejected_registry"])
async def test_financial_registry_mapping_refusal_commits_no_capture_or_terminal_fact(
    neutral_lease,
    mapping,
):
    lease = neutral_lease
    mappings = (
        [None]
        if mapping == "missing"
        else ([lease.portfolio, lease.portfolio] if mapping == "ambiguous" else [lease.portfolio])
    )
    chunks, registry = registry_commands(lease, mappings)
    await stage_chunks_and_seal(lease, chunks, registry)
    if mapping == "rejected_registry":
        repository = FinancialSourceCutWorkRepository(lease.sessions)
        await repository.reject(await repository.claim())
    else:
        await drive_work(lease, ForbiddenSourceClient())
    financial_chunks, financial = financial_commands(lease, registry)
    if mapping == "wrong_root":
        record = selected_input(lease.portfolio, "b" * 64)
        financial_chunks = [
            FinancialChunkInput(
                **financial_chunks[0].model_dump(exclude={"selections", "typed_content_hash"}),
                selections=(record,),
                typed_content_hash=canonical_content_hash(
                    {
                        "contract": "PortfolioFinancialSourceCutChunk:v1",
                        "selections": [record.model_dump(mode="json")],
                    }
                ),
            )
        ]
        financial = FinancialSealInput.model_validate(
            financial.model_dump()
            | dict(
                selections_root=ordered_content_root(
                    "PortfolioFinancialSourceCutInputs:v1",
                    [source_stager.financial_input_hash(record)],
                )[1],
                chunks_root=ordered_content_root(
                    "NeutralSourceChunks:v1", [financial_chunks[0].typed_content_hash]
                )[1],
            )
        )
    job, _ = await stage_chunks_and_seal(lease, financial_chunks, financial)
    await drive_work(lease, ForbiddenSourceClient())
    async with lease.sessions() as session:
        rejected = await session.scalar(
            select(IngestionJob).where(IngestionJob.job_id == job.job_id)
        )
        assert rejected.status == "failed" and rejected.completed_at is None
        assert (
            await session.scalar(select(func.count()).select_from(FinancialSourceCaptureRow)) == 0
        )
        assert (
            await session.scalar(select(func.count()).select_from(FinancialSourceCaptureLinkRow))
            == 0
        )
        assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == (
            0 if mapping == "rejected_registry" else 1
        )


@pytest.mark.parametrize("mutation", ["foreign_portfolio", "descending", "cross_chunk_duplicate"])
async def test_native_chunk_refusal_rolls_back_receipt_and_all_creation_effects(
    neutral_lease,
    mutation,
):
    lease = neutral_lease
    chunks, _ = registry_commands(lease, [lease.portfolio, None])
    if mutation == "foreign_portfolio":
        foreign = lease.portfolio + "-foreign"
        await add_portfolio(lease, foreign, tenant="synthetic-other-tenant")
        chunks, _ = registry_commands(lease, [foreign])
        rejected = chunks[0]
    elif mutation == "descending":
        records = (chunks[1].members[0], chunks[0].members[0])
        rejected = RegistryChunkInput(
            **chunks[0].model_dump(exclude={"members", "typed_content_hash"}),
            members=records,
            typed_content_hash=canonical_content_hash(
                {
                    "contract": "PortfolioHistoricalRegistryChunk:v1",
                    "members": [member.to_domain().content_hash for member in records],
                }
            ),
        )
    else:
        await stage_command(lease, chunks[0])
        rejected = RegistryChunkInput.model_validate(chunks[0].model_dump() | {"chunk_index": 1})
    before = await native_state(lease)
    with pytest.raises(
        ObservationConflict,
        match="SOURCE_MEMBER_PORTFOLIO_NOT_OWNED|SOURCE_CHUNK_ORDER_OR_DUPLICATE",
    ):
        await stage_command(lease, rejected)
    assert await native_state(lease) == before


async def test_chunk_replay_preserves_original_receipt_and_raw_divergence_has_no_orphan_job(
    neutral_lease,
):
    lease = neutral_lease
    chunks, _ = registry_commands(lease)
    key = str(uuid4())
    original, stager = await stage_command(lease, chunks[0], idempotency=key)
    before = await native_state(lease)
    replay, _ = await stage_command(lease, chunks[0], idempotency=key)
    assert replay.job_id == original.job_id
    assert await stager.original_receipt(lease.sessions) == original.job_id
    with pytest.raises(ObservationConflict, match="SOURCE_CUT_DIVERGENT_REPLAY"):
        await stage_command(lease, chunks[0], raw_bytes=stager.raw_bytes + b" ")
    assert await native_state(lease) == before


@pytest.mark.parametrize("mutation", ["index_gap", "population", "chunk_count"])
async def test_seal_cardinality_refusal_keeps_staged_history_and_rolls_back_new_receipt(
    neutral_lease,
    mutation,
):
    lease = neutral_lease
    chunks, seal = registry_commands(lease)
    if mutation == "index_gap":
        chunks = [RegistryChunkInput.model_validate(chunks[0].model_dump() | {"chunk_index": 1})]
    elif mutation == "population":
        seal = RegistrySealInput.model_validate(seal.model_dump() | {"supplied_count": 2})
    else:
        seal = RegistrySealInput.model_validate(seal.model_dump() | {"chunk_count": 2})
    await stage_command(lease, chunks[0])
    before = await native_state(lease)
    with pytest.raises(ObservationConflict, match="SOURCE_SEAL_CHUNK_CARDINALITY_MISMATCH"):
        await stage_command(lease, seal)
    assert await native_state(lease) == before


async def test_retained_raw_chunk_substitution_rejects_seal_without_outbox(neutral_lease):
    lease = neutral_lease
    chunks, seal = registry_commands(lease)
    body = chunks[0].model_dump(mode="json")
    body["members"][0]["declarations"][0]["included"] = False
    await stage_command(lease, chunks[0], raw_bytes=json.dumps(body).encode())
    job, _ = await stage_command(lease, seal)
    await drive_work(lease, ForbiddenSourceClient())
    async with lease.sessions() as session:
        rejected = await session.scalar(
            select(IngestionJob).where(IngestionJob.job_id == job.job_id)
        )
        assert rejected.status == "failed" and rejected.completed_at is None
        assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 0


async def test_actual_cas_race_retains_one_correction_and_no_losing_receipt(neutral_lease):
    lease = neutral_lease
    original = registry_request()
    await stage_registry(lease, original)
    await finish_registry(lease)
    parent = original.to_domain(lease.tenant).content_hash
    corrections = [
        RegistrySealInput.model_validate(
            registry_request(revision=2, predecessor=parent).model_dump()
            | {"definition_version": version}
        )
        for version in ("synthetic-correction-a", "synthetic-correction-b")
    ]
    outcomes = await asyncio.gather(
        *(stage_registry(lease, request) for request in corrections), return_exceptions=True
    )
    assert sum(isinstance(outcome, ObservationConflict) for outcome in outcomes) == 1
    assert sum(isinstance(outcome, tuple) for outcome in outcomes) == 1
    async with lease.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(IngestionJob)) == 2
        assert await session.scalar(select(func.count()).select_from(FinancialSourceCutRow)) == 2
        assert (
            await session.scalar(select(func.count()).select_from(FinancialSourceCutWorkRow)) == 2
        )
        head = await session.scalar(select(FinancialSourceHeadRow))
        assert head.revision == 2 and head.content_hash in {
            request.to_domain(lease.tenant).content_hash for request in corrections
        }
    await drive_work(lease, ForbiddenSourceClient())
    before = await native_state(lease)
    with pytest.raises(ObservationConflict, match="SOURCE_SEAL_STALE_HEAD"):
        await stage_registry(lease, registry_request(revision=3, predecessor=parent))
    assert await native_state(lease) == before


@pytest.mark.parametrize("mutation", ["expired", "token", "checkpoint", "root"])
async def test_acquired_capture_cannot_cross_a_stale_database_fence(neutral_lease, mutation):
    lease = neutral_lease
    await populated_financial_case(lease)
    repository = FinancialSourceCutWorkRepository(lease.sessions)
    claim, request = await next_capture_claim(lease, repository)
    page = await SyntheticCapturePort().fetch(request)
    if mutation in {"expired", "checkpoint"}:
        async with lease.sessions.begin() as session:
            row = await session.get(FinancialSourceCutWorkRow, claim.work_id)
            if mutation == "expired":
                row.lease_expires_at = await session.scalar(
                    select(func.clock_timestamp())
                ) - timedelta(seconds=1)
            else:
                row.checkpoint = dict(row.checkpoint, interrupted=True)
    elif mutation == "token":
        claim = replace(claim, lease_token=str(uuid4()))
    else:
        claim = replace(claim, command_hash="b" * 64)
    before = await native_state(lease)
    try:
        with pytest.raises(StaleSourceCutClaim):
            await repository.save_capture(claim, page)
    finally:
        page.capture_bytes.close()
    assert await native_state(lease) == before


@pytest.mark.parametrize("mutation", ["request", "epoch", "scope", "total", "incomplete", "excess"])
async def test_capture_page_substitution_rolls_back_bytes_links_and_checkpoint(
    neutral_lease,
    mutation,
):
    lease = neutral_lease
    await populated_financial_case(lease)
    repository = FinancialSourceCutWorkRepository(lease.sessions)
    claim, request = await next_capture_claim(lease, repository)
    first = await SyntheticCapturePort().fetch(request)
    try:
        await repository.save_capture(claim, first)
    finally:
        first.capture_bytes.close()
    claim, request = await next_capture_claim(lease, repository)
    assert request.page_index == 1 and request.page_token == "next-page"
    page = await SyntheticCapturePort().fetch(request)
    changes = {
        "request": {"request": replace(request, currency="EUR")},
        "epoch": {"snapshot_epoch": "18"},
        "scope": {"request_scope": "substituted"},
        "total": {"total_count": 3},
        "incomplete": {"returned_count": 0},
        "excess": {"returned_count": 2},
    }[mutation]
    page = replace(page, **changes)
    before = await native_state(lease)
    try:
        with pytest.raises(
            SourceCaptureUnavailable,
            match="SOURCE_CAPTURE_REQUEST_SUBSTITUTION|SOURCE_CAPTURE_MIXED_EPOCH_OR_SCOPE|SOURCE_CAPTURE_INCOMPLETE_COVERAGE",
        ):
            await repository.save_capture(claim, page)
    finally:
        page.capture_bytes.close()
    assert await native_state(lease) == before


async def root_claim_after_spawn(lease, repository):
    # Advance actual stages, leaving spawned captures unexecuted for terminal refusal proofs.
    for _ in range(12):
        claim = await repository.claim()
        request = await repository.next_capture(claim)
        assert isinstance(request, SourceCutProgress)
        await repository.advance(claim, request)
        if request.stage == "SPAWN_CAPTURES":
            break
    else:
        raise AssertionError("financial parent did not spawn bounded partitions")
    async with lease.sessions.begin() as session:
        await session.execute(
            update(FinancialSourceCutWorkRow)
            .where(
                FinancialSourceCutWorkRow.product_name == "PortfolioFinancialSourceCut",
                FinancialSourceCutWorkRow.partition_index > 0,
            )
            .values(available_at=func.clock_timestamp() + timedelta(seconds=60))
        )
        await session.execute(
            update(FinancialSourceCutWorkRow)
            .where(
                FinancialSourceCutWorkRow.product_name == "PortfolioFinancialSourceCut",
                FinancialSourceCutWorkRow.partition_index == 0,
            )
            .values(available_at=func.clock_timestamp())
        )
    return await repository.claim()


@pytest.mark.parametrize("partition_state", ["pending", "failed"])
async def test_parent_cannot_complete_or_emit_with_incomplete_capture_partitions(
    neutral_lease,
    partition_state,
):
    lease = neutral_lease
    _, _, job, _ = await populated_financial_case(lease)
    repository = FinancialSourceCutWorkRepository(lease.sessions)
    claim = await root_claim_after_spawn(lease, repository)
    if partition_state == "failed":
        async with lease.sessions.begin() as session:
            await session.execute(
                update(FinancialSourceCutWorkRow)
                .where(FinancialSourceCutWorkRow.partition_index > 0)
                .values(status="FAILED")
            )
        with pytest.raises(SourceManifestRejected, match="SOURCE_CAPTURE_PARTITION_REJECTED"):
            await repository.advance(claim, SourceCutProgress("WAIT_CAPTURES"))
        await repository.reject(claim)
    else:
        with pytest.raises(SourceCaptureUnavailable, match="SOURCE_CUT_MANIFEST_INCOMPLETE"):
            await repository.complete(claim)
        # A READY checkpoint alone cannot substitute for persisted terminal partitions.
        async with lease.sessions.begin() as session:
            row = await session.get(FinancialSourceCutWorkRow, claim.work_id)
            row.checkpoint = dict(row.checkpoint, stage="READY")
            row.status, row.lease_token, row.lease_expires_at = "PENDING", None, None
        ready = await repository.claim()
        with pytest.raises(SourceCaptureUnavailable, match="SOURCE_CAPTURE_PARTITIONS_PENDING"):
            await repository.complete(ready)
    async with lease.sessions() as session:
        actual = await session.scalar(select(IngestionJob).where(IngestionJob.job_id == job.job_id))
        assert actual.status == ("failed" if partition_state == "failed" else "accepted")
        assert actual.completed_at is None
        assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(FinancialSourceCaptureLinkRow))
            == 0
        )


async def test_terminal_receipt_mismatch_rolls_back_outbox_and_work_completion(neutral_lease):
    lease = neutral_lease
    job, _ = await stage_registry(lease, registry_request())
    repository = FinancialSourceCutWorkRepository(lease.sessions)
    for _ in range(2):
        claim = await repository.claim()
        await repository.advance(claim, await repository.next_capture(claim))
    claim = await repository.claim()
    assert await repository.next_capture(claim) is None
    async with lease.sessions.begin() as session:
        await session.execute(
            update(IngestionJob).where(IngestionJob.job_id == job.job_id).values(status="failed")
        )
    before = await native_state(lease)
    with pytest.raises(SourceManifestRejected, match="SOURCE_CUT_RECEIPT_STATE_MISMATCH"):
        await repository.complete(claim)
    assert await native_state(lease) == before


async def test_registry_member_verification_resumes_a_bounded_persisted_checkpoint(neutral_lease):
    lease = neutral_lease
    chunks, seal = registry_commands(lease, [lease.portfolio] + [None] * 500, page_size=500)
    assert [len(chunk.members) for chunk in chunks] == [500, 1]
    job, _ = await stage_chunks_and_seal(lease, chunks, seal)
    repository = FinancialSourceCutWorkRepository(lease.sessions)
    pages = []
    for _ in range(10):
        claim = await repository.claim()
        assert claim is not None
        progress = await repository.next_capture(claim)
        if progress is None:
            await repository.complete(claim)
            break
        assert isinstance(progress, SourceCutProgress)
        await repository.advance(claim, progress)
        if progress.stage == "VERIFY_MEMBERS":
            async with lease.sessions() as session:
                work = await session.get(FinancialSourceCutWorkRow, claim.work_id)
                pages.append(dict(work.checkpoint))
    else:
        raise AssertionError("bounded registry verification did not complete")
    assert len(pages) == 2
    assert pages[0]["stage"] == "VERIFY_MEMBERS"
    assert pages[0]["ordered_root_checkpoint"][1] == 500
    assert pages[0]["last_member_key"] == ["synthetic-provider", "member-0499"]
    assert pages[1]["stage"] == "READY" and pages[1]["ordered_root_checkpoint"] is None
    assert pages[1]["last_member_key"] == ["synthetic-provider", "member-0500"]
    async with lease.sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(HistoricalRegistryMemberRow))
            == 501
        )
        actual = await session.scalar(select(IngestionJob).where(IngestionJob.job_id == job.job_id))
        assert actual.status == "completed"
        event = await session.scalar(select(OutboxEvent))
        assert event.payload["content_hash"] == seal.to_domain(lease.tenant).content_hash
        assert event.payload["population_verification"] == "UNVERIFIED"


async def test_financial_work_defers_until_original_registry_custody_completes(neutral_lease):
    lease = neutral_lease
    chunks, registry = registry_commands(lease)
    await stage_chunks_and_seal(lease, chunks, registry)
    async with lease.sessions.begin() as session:
        await session.execute(
            update(FinancialSourceCutWorkRow)
            .where(FinancialSourceCutWorkRow.product_name == "PortfolioHistoricalRegistry")
            .values(available_at=func.clock_timestamp() + timedelta(seconds=60))
        )
    chunks, financial = financial_commands(lease, registry)
    job, _ = await stage_chunks_and_seal(lease, chunks, financial)
    processor = FinancialSourceCutProcessor(
        FinancialSourceCutWorkRepository(lease.sessions), ForbiddenSourceClient()
    )
    for _ in range(3):
        assert await processor.step()
    async with lease.sessions() as session:
        root = await session.scalar(
            select(FinancialSourceCutWorkRow).where(
                FinancialSourceCutWorkRow.product_name == "PortfolioFinancialSourceCut"
            )
        )
        assert root.status == "PENDING" and root.checkpoint["stage"] == "VERIFY_INPUTS"
        assert root.last_error_code == "SOURCE_CAPTURE_UNAVAILABLE"
        assert (
            await session.scalar(select(func.count()).select_from(FinancialSourceCaptureRow)) == 0
        )
        assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 0
        actual = await session.scalar(select(IngestionJob).where(IngestionJob.job_id == job.job_id))
        assert actual.status == "accepted" and actual.completed_at is None
    await make_pending_work_available(lease)
    await drive_work(lease, SyntheticCapturePort())
    async with lease.sessions() as session:
        actual = await session.scalar(select(IngestionJob).where(IngestionJob.job_id == job.job_id))
        assert actual.status == "completed"
        assert await session.scalar(select(func.count()).select_from(OutboxEvent)) == 2
