"""Exercise a committed source correction while an older valuation is in flight."""

import asyncio
import json
from dataclasses import asdict, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import httpx
import pytest
from portfolio_common.database_models import (
    BusinessDate,
    DailyPositionSnapshot,
    DailyPositionValuationReceiptRecord,
    FxRate,
    Instrument,
    MarketPriceSourceFactRecord,
    OutboxEvent,
    Portfolio,
    PortfolioValuationJob,
    PositionHistory,
    PositionState,
    ProcessedEvent,
    Transaction,
)
from portfolio_common.db import get_async_db_session
from portfolio_common.domain.valuation import canonical_content_hash
from portfolio_common.events import FxRateEvent, PortfolioValuationRequiredEvent
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.valuation_job_repository import ValuationJobRepository
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.services.calculators.position_valuation_calculator.app.infrastructure import (
    SqlAlchemyValuationProcessorDependencyFactory,
    build_valuation_job_processor,
)
from src.services.calculators.position_valuation_calculator.app.repositories import (
    valuation_repository,
)
from src.services.ingestion_service.app.services.reference_data_ingestion_service import (
    ReferenceDataIngestionService,
)
from src.services.persistence_service.app.consumers import base_consumer
from src.services.persistence_service.app.consumers.fx_rate_consumer import FxRateConsumer
from src.services.query_control_plane_service.app.main import app
from src.services.valuation_orchestrator_service.app.adapters.kafka import (
    fx_rate_persisted_consumer,
)
from src.services.valuation_orchestrator_service.app.consumers import price_event_consumer

pytestmark = [pytest.mark.asyncio, pytest.mark.db_direct, pytest.mark.lifecycle]

DAY = date(2026, 7, 22)
TENANT = "CORE788_WINDOW_TENANT"
BOOK = "CORE788_WINDOW_BOOK"
PORTFOLIO = "CORE788_WINDOW_PORTFOLIO"
SECURITY = "CORE788_WINDOW_SECURITY"
TRANSACTION = "CORE788_WINDOW_BUY"
CORRELATION = "core788-correction-window"


def _price(version: int, price: str) -> dict:
    content = {"security_id": SECURITY, "price_date": DAY, "price": Decimal(price)}
    return {
        **content,
        "tenant_id": TENANT,
        "legal_book_id": BOOK,
        "currency": "EUR",
        "quote_basis": "UNIT_PRICE",
        "fact_status": "ACTIVE",
        "fact_version": version,
        "source_system": "core788-approved-price",
        "source_record_id": "core788-window-price",
        "source_revision": f"C{version}",
        "source_content_hash": canonical_content_hash(content),
        "observed_at": datetime(2026, 7, 22, version, tzinfo=UTC),
    }


def _message(payload: dict, *, topic: str, offset: int):
    """Model transport only; all financial handlers remain production code."""
    message = MagicMock()
    message.value.return_value = json.dumps(payload, default=str).encode()
    message.key.return_value = b"EUR-USD"
    message.topic.return_value = topic
    message.partition.return_value = 0
    message.offset.return_value = offset
    message.headers.return_value = [("correlation_id", CORRELATION.encode())]
    return message


async def _seed_inputs(session):
    session.add_all(
        [
            BusinessDate(date=DAY),
            Portfolio(
                tenant_id=TENANT,
                legal_book_id=BOOK,
                portfolio_id=PORTFOLIO,
                base_currency="USD",
                open_date=date(2026, 1, 1),
                risk_exposure="MODERATE",
                investment_time_horizon="LONG_TERM",
                portfolio_type="DISCRETIONARY",
                booking_center_code="SG",
                client_id="CORE788_WINDOW_CLIENT",
                status="ACTIVE",
            ),
            Instrument(
                security_id=SECURITY,
                name="Correction-window equity",
                isin="XS788WINDOW01",
                currency="EUR",
                product_type="COMMON_STOCK",
                asset_class="EQUITY",
            ),
        ]
    )
    await session.flush()
    session.add(
        Transaction(
            transaction_id=TRANSACTION,
            portfolio_id=PORTFOLIO,
            security_id=SECURITY,
            instrument_id=SECURITY,
            transaction_date=datetime(2026, 7, 22, tzinfo=UTC),
            transaction_type="BUY",
            quantity=Decimal("10"),
            price=Decimal("100"),
            gross_transaction_amount=Decimal("1000"),
            trade_currency="EUR",
            currency="EUR",
        )
    )
    await session.flush()
    session.add_all(
        [
            PositionHistory(
                transaction_id=TRANSACTION,
                portfolio_id=PORTFOLIO,
                security_id=SECURITY,
                position_date=DAY,
                epoch=0,
                quantity=Decimal("10"),
                cost_basis=Decimal("1000"),
                cost_basis_local=Decimal("1000"),
            ),
            PositionState(
                portfolio_id=PORTFOLIO,
                security_id=SECURITY,
                epoch=0,
                watermark_date=DAY,
                status="CURRENT",
            ),
        ]
    )
    await session.commit()
    await ReferenceDataIngestionService(session).append_instrument_valuation_policy_assignments(
        [
            {
                "tenant_id": TENANT,
                "legal_book_id": BOOK,
                "security_id": SECURITY,
                "policy_id": "UNIT_PRICE_MARKET_VALUE",
                "policy_version": 1,
                "valid_from": DAY,
                "assignment_status": "ACTIVE",
                "assignment_version": 1,
                "source_system": "core788-security-master",
                "source_record_id": "core788-policy",
                "source_revision": "policy-1",
                "observed_at": datetime(2026, 7, 22, tzinfo=UTC),
                "assignment_reason": "Explicit unit-price equity treatment",
            }
        ]
    )


class _CaptureFactory(SqlAlchemyValuationProcessorDependencyFactory):
    def __init__(self):
        self.vectors = []

    def from_session(self, db):
        dependencies = super().from_session(db)

        def capture(**inputs):
            evidence = dependencies.source_evidence_builder(**inputs)
            self.vectors.append(
                {
                    "tenant": inputs["portfolio"].tenant_id,
                    "book": inputs["portfolio"].legal_book_id,
                    "epoch": inputs["position"].epoch,
                    "assignment_version": inputs["assignment"].assignment.assignment_version,
                    "price_fact_version": inputs["price_fact"].fact_version,
                    "evidence": asdict(evidence),
                }
            )
            return evidence

        return replace(dependencies, source_evidence_builder=capture)


async def _claim(sessions):
    async with sessions() as session, session.begin():
        jobs = await valuation_repository.ValuationRepository(session).find_and_claim_eligible_jobs(
            1,
            lease_owner=CORRELATION,
        )
        assert len(jobs) == 1, "Production claim must return the correction-window job"
        return jobs[0].valuation_claim_token


async def _read_current(sessions):
    async def reader_session():
        async with sessions() as session:
            yield session

    assert get_async_db_session not in app.dependency_overrides
    app.dependency_overrides[get_async_db_session] = reader_session
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://core788",
        ) as client:
            response = await client.post(
                f"/integration/portfolios/{PORTFOLIO}/core-snapshot",
                headers={"X-Tenant-Id": TENANT},
                json={
                    "tenant_id": TENANT,
                    "consumer_system": "lotus-advise",
                    "as_of_date": DAY.isoformat(),
                    "snapshot_mode": "BASELINE",
                    "reporting_currency": "USD",
                    "sections": ["portfolio_state", "portfolio_totals"],
                },
            )
            assert response.status_code == 200, response.text
            return response.json()
    finally:
        app.dependency_overrides.pop(get_async_db_session)


async def test_dated_source_cut_retains_coherence_without_current_certification(
    clean_db,
    async_db_session,
    monkeypatch,
):
    """Date READY is coherent timing, not a latest-revision publication certificate.

    Root corrected the original red premise; exact source/log remain external diagnostics.
    Retain both vectors/cutoffs and actual overall qualification and FX recovery.
    """
    sessions = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async def session_provider():
        async with sessions() as session:
            yield session

    monkeypatch.setattr(base_consumer, "get_async_db_session", session_provider)
    monkeypatch.setattr(fx_rate_persisted_consumer, "get_async_db_session", session_provider)
    fx_writer = FxRateConsumer("unused:9092", "fx_rates", CORRELATION)

    async def write_sources(version, price, rate):
        async with sessions() as writer:
            await ReferenceDataIngestionService(
                writer
            ).append_authoritative_market_price_source_facts([_price(version, price)])
        observation = FxRateEvent(from_currency="EUR", to_currency="USD", rate_date=DAY, rate=rate)
        await fx_writer.process_message(
            _message(
                observation.model_dump(mode="json"),
                topic="fx_rates",
                offset=version,
            )
        )

    await _seed_inputs(async_db_session)
    await write_sources(1, "100", "1")
    async with sessions() as scheduler, scheduler.begin():
        await ValuationJobRepository(scheduler).upsert_job(
            portfolio_id=PORTFOLIO,
            security_id=SECURITY,
            valuation_date=DAY,
            epoch=0,
            correlation_id=CORRELATION,
        )
    token = await _claim(sessions)
    event = PortfolioValuationRequiredEvent(
        portfolio_id=PORTFOLIO,
        security_id=SECURITY,
        valuation_date=DAY,
        epoch=0,
    )
    capture = _CaptureFactory()
    worker = build_valuation_job_processor(
        session_provider=session_provider, dependency_factory=capture
    )
    selected, release = asyncio.Event(), asyncio.Event()
    complete = worker._complete_valuation_job
    cutoff = {}

    async def selection_barrier(repo, worker_event, result, *, claim_token):
        assert result.snapshot.market_value == Decimal("1000"), "Independent 1000/C1 oracle"
        assert result.receipt.price_fact_version == 1
        cutoff["C1"] = await repo.db.scalar(select(func.clock_timestamp()))
        selected.set()
        await asyncio.wait_for(release.wait(), timeout=30)
        return await complete(repo, worker_event, result, claim_token=claim_token)

    monkeypatch.setattr(worker, "_complete_valuation_job", selection_barrier)
    task = asyncio.create_task(
        worker.process_valid_event(event, "core788-W1", CORRELATION, claim_token=token)
    )
    try:
        await asyncio.wait_for(selected.wait(), timeout=30)
        await write_sources(2, "120", "1.1")
        async with sessions() as reader:
            cutoff["C2"] = await reader.scalar(select(func.clock_timestamp()))
            current_fx = await reader.scalar(select(FxRate).where(FxRate.rate_date == DAY))
            assert current_fx.rate == Decimal("1.1")
        assert cutoff["C2"] > cutoff["C1"]
        release.set()
        await asyncio.wait_for(task, timeout=30)
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    current = await _read_current(sessions)
    async with sessions() as reader:
        snapshot = await reader.scalar(select(DailyPositionSnapshot))
        receipt = await reader.scalar(select(DailyPositionValuationReceiptRecord))
        publication_count = await reader.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(
                OutboxEvent.event_type == "DailyPositionSnapshotPersisted",
            )
        )
        print(
            "CORE788_WINDOW="
            + json.dumps(
                {
                    "cutoffs": cutoff,
                    "selected_vectors": capture.vectors,
                    "snapshot_value": snapshot.market_value if snapshot else None,
                    "snapshot_status": snapshot.valuation_status if snapshot else None,
                    "receipt_price_version": receipt.price_fact_version if receipt else None,
                    "receipt_lineage": receipt.calculation_lineage if receipt else None,
                    "valuation_publications": publication_count,
                    "qcp": current,
                },
                default=str,
                sort_keys=True,
            )
        )
        # No reconciliation controls are seeded: report their actual qualification.
        # Test freshness independently of that unrelated readiness prerequisite.
        c1_date_coherent = (
            snapshot is not None
            and snapshot.market_value == Decimal("1000")
            and current["valuation_context"]["supportability"] == "READY"
        )
        correction = await reader.scalar(
            select(OutboxEvent)
            .where(
                OutboxEvent.event_type == "FxRatePersisted",
            )
            .order_by(OutboxEvent.id.desc())
        )
        correction_payload = correction.payload

    # Deliver only the actual durable correction, then reconstruct the worker.
    trigger = fx_rate_persisted_consumer.FxRatePersistedConsumer(
        "unused:9092",
        "fx_rates.persisted",
        CORRELATION,
    )
    await trigger.process_message(
        _message(correction_payload, topic="fx_rates.persisted", offset=2)
    )
    fresh_token = await _claim(sessions)
    fresh_worker = build_valuation_job_processor(
        session_provider=session_provider, dependency_factory=capture
    )
    await fresh_worker.process_valid_event(
        event, "core788-W2", CORRELATION, claim_token=fresh_token
    )
    async with sessions() as reader:
        corrected = await reader.scalar(select(DailyPositionSnapshot))
        corrected_receipt = await reader.scalar(select(DailyPositionValuationReceiptRecord))
        assert corrected.market_value == Decimal("1320"), "Independent 1320/C2 oracle"
        assert corrected_receipt.price_fact_version == 2
        assert capture.vectors[0] != capture.vectors[-1]
    print(
        "CORE788_RECOVERY="
        + json.dumps({"value": "1320", "vector": capture.vectors[-1]}, default=str)
    )
    assert c1_date_coherent
    assert current["source_evidence_current"] is False
    assert current["reconciliation_status"] == "UNRECONCILED"
    assert current["data_quality_status"] == "UNKNOWN"


async def test_scoped_price_fanout_pages_moves_withdrawal_and_atomic_rollback(
    clean_db,
    async_db_session,
    monkeypatch,
):
    """Real PG transactions retain every page and isolate both authority dimensions."""
    sessions = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async def provider():
        async with sessions() as db:
            yield db

    monkeypatch.setattr(price_event_consumer, "get_async_db_session", provider)
    async with sessions() as db:
        await _seed_inputs(db)
        template = await db.scalar(select(Portfolio).where(Portfolio.portfolio_id == PORTFOLIO))
        expected = {PORTFOLIO}
        excluded = set()
        for index in range(106):
            portfolio_id = f"CORE788_PAGE_{index:03}"
            values = {
                column.name: getattr(template, column.name)
                for column in Portfolio.__table__.columns
                if not column.primary_key
            }
            values["portfolio_id"] = portfolio_id
            if index == 102:
                values["tenant_id"] = "OTHER_TENANT"
            if index == 103:
                values["legal_book_id"] = "OTHER_BOOK"
            if index < 102:
                expected.add(portfolio_id)
            else:
                excluded.add(portfolio_id)
            db.add(Portfolio(**values))
            await db.flush()
            db.add_all(
                [
                    PositionState(
                        portfolio_id=portfolio_id,
                        security_id=SECURITY,
                        epoch=0,
                        watermark_date=DAY,
                        status="CURRENT",
                    ),
                    PositionHistory(
                        transaction_id=TRANSACTION,
                        portfolio_id=portfolio_id,
                        security_id=SECURITY,
                        position_date=DAY,
                        epoch=1 if index == 105 else 0,
                        quantity=Decimal("0" if index == 104 else "-10" if index == 101 else "10"),
                        cost_basis=Decimal("1000"),
                        cost_basis_local=Decimal("1000"),
                    ),
                ]
            )
        await db.commit()
        await ReferenceDataIngestionService(db).append_authoritative_market_price_source_facts(
            [_price(1, "100")]
        )

    async def payloads(version):
        async with sessions() as db:
            rows = (
                await db.scalars(
                    select(OutboxEvent)
                    .where(OutboxEvent.event_type == "AuthoritativeMarketPriceAuthorityChanged")
                    .order_by(OutboxEvent.id)
                )
            ).all()
            return [
                row.payload for row in rows if row.payload["accepted"]["fact_version"] == version
            ]

    consumer = price_event_consumer.PriceEventConsumer(
        "unused:9092", "market_prices.persisted", CORRELATION
    )
    initial = (await payloads(1))[0]
    actual_upsert = ValuationJobRepository.upsert_jobs
    calls = 0

    async def fail_second_page(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("second-page failure")
        return await actual_upsert(self, *args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(ValuationJobRepository, "upsert_jobs", fail_second_page)
        with pytest.raises(RuntimeError, match="second-page failure"):
            await consumer.process_message(
                _message(initial, topic="market_prices.persisted", offset=1)
            )
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(PortfolioValuationJob)) == 0
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ProcessedEvent)
                .where(ProcessedEvent.event_id == initial["correction_id"])
            )
            == 0
        )
    await consumer.process_message(_message(initial, topic="market_prices.persisted", offset=2))
    async with sessions() as db:
        jobs = (await db.scalars(select(PortfolioValuationJob))).all()
        assert {job.portfolio_id for job in jobs} == expected
        assert len(jobs) == 103 > price_event_consumer.AUTHORITATIVE_PRICE_IMPACT_PAGE_SIZE
        assert excluded.isdisjoint(job.portfolio_id for job in jobs)

    # Exact source duplicates create no second intent. A newer price remains the
    # persisted authority even when older correction messages arrive afterwards.
    async with sessions() as db:
        service = ReferenceDataIngestionService(db)
        await service.append_authoritative_market_price_source_facts([_price(1, "100")])
        await service.append_authoritative_market_price_source_facts([_price(2, "120")])
        await service.append_authoritative_market_price_source_facts([_price(3, "130")])
    assert len(await payloads(1)) == 1
    for payload in [(await payloads(3))[0], (await payloads(2))[0], initial, initial]:
        await consumer.process_message(_message(payload, topic="market_prices.persisted", offset=3))
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(PortfolioValuationJob)) == 103
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ProcessedEvent)
                .where(ProcessedEvent.service_name == "price-event-reprocessing-trigger-authority")
            )
            == 3
        )

    # Same source key moves between scoped authorities: both old and new scope
    # receive intents; neither uses security-global replay.
    moved = {**_price(4, "140"), "tenant_id": "OTHER_TENANT"}
    async with sessions() as db:
        await ReferenceDataIngestionService(db).append_authoritative_market_price_source_facts(
            [moved]
        )
        await db.execute(delete(PortfolioValuationJob))
        await db.commit()
    moves = await payloads(4)
    assert {payload["tenant_id"] for payload in moves} == {TENANT, "OTHER_TENANT"}
    for payload in reversed(moves):
        await consumer.process_message(_message(payload, topic="market_prices.persisted", offset=4))
    async with sessions() as db:
        jobs = (await db.scalars(select(PortfolioValuationJob))).all()
        assert {job.portfolio_id for job in jobs} == expected | {"CORE788_PAGE_102"}

    withdrawn = {**moved, "fact_version": 5, "source_revision": "C5", "fact_status": "RETIRED"}
    async with sessions() as db:
        await ReferenceDataIngestionService(db).append_authoritative_market_price_source_facts(
            [withdrawn]
        )
        await db.execute(delete(PortfolioValuationJob))
        await db.commit()
    withdrawal = (await payloads(5))[0]
    await consumer.process_message(_message(withdrawal, topic="market_prices.persisted", offset=5))
    async with sessions() as db:
        jobs = (await db.scalars(select(PortfolioValuationJob))).all()
        assert [job.portfolio_id for job in jobs] == ["CORE788_PAGE_102"]

    # Outbox failure must roll back the accepted fact as well as the intent.
    original_outbox = OutboxRepository.create_outbox_event

    async def reject_outbox(self, **kwargs):
        await original_outbox(self, **kwargs)
        raise RuntimeError("source/outbox rollback")

    with monkeypatch.context() as patcher:
        patcher.setattr(OutboxRepository, "create_outbox_event", reject_outbox)
        async with sessions() as db:
            with pytest.raises(RuntimeError, match="source/outbox rollback"):
                await ReferenceDataIngestionService(
                    db
                ).append_authoritative_market_price_source_facts(
                    [{**moved, "fact_version": 6, "source_revision": "C6"}]
                )
    assert not await payloads(6)
    async with sessions() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(MarketPriceSourceFactRecord)
                .where(MarketPriceSourceFactRecord.fact_version == 6)
            )
            == 0
        )
    print(
        "CORE788_SCOPED_CONTROLS=103 positions; pages>1; rollback; duplicates; "
        "out-of-order; old/new tenant; withdrawal; book isolation"
    )


async def test_authoritative_price_only_correction_stages_durable_revaluation(
    clean_db,
    async_db_session,
    monkeypatch,
):
    """A committed price correction must own durable work without an FX rescue."""
    from portfolio_common.database_models import (
        InstrumentReprocessingState,
        MarketPriceSourceFactRecord,
        PortfolioValuationJob,
        ReprocessingJob,
    )

    sessions = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async def session_provider():
        async with sessions() as session:
            yield session

    monkeypatch.setattr(base_consumer, "get_async_db_session", session_provider)
    monkeypatch.setattr(price_event_consumer, "get_async_db_session", session_provider)
    await _seed_inputs(async_db_session)
    async with sessions() as writer:
        await ReferenceDataIngestionService(writer).append_authoritative_market_price_source_facts(
            [_price(1, "100")]
        )
    initial_fx = FxRateEvent(
        from_currency="EUR",
        to_currency="USD",
        rate_date=DAY,
        rate="1",
    )
    await FxRateConsumer("unused:9092", "fx_rates", CORRELATION).process_message(
        _message(initial_fx.model_dump(mode="json"), topic="fx_rates", offset=1)
    )
    async with sessions() as scheduler, scheduler.begin():
        await ValuationJobRepository(scheduler).upsert_job(
            portfolio_id=PORTFOLIO,
            security_id=SECURITY,
            valuation_date=DAY,
            epoch=0,
            correlation_id=CORRELATION,
        )
    token = await _claim(sessions)
    event = PortfolioValuationRequiredEvent(
        portfolio_id=PORTFOLIO,
        security_id=SECURITY,
        valuation_date=DAY,
        epoch=0,
    )
    capture = _CaptureFactory()
    worker = build_valuation_job_processor(
        session_provider=session_provider,
        dependency_factory=capture,
    )
    await worker.process_valid_event(
        event,
        "core788-price-only-initial",
        CORRELATION,
        claim_token=token,
    )
    async with sessions() as reader:
        initial = await reader.scalar(select(DailyPositionSnapshot))
        receipt = await reader.scalar(select(DailyPositionValuationReceiptRecord))
        initial_job = await reader.scalar(select(PortfolioValuationJob))
        assert initial.market_value == Decimal("1000"), "Independent initial 1000 oracle"
        assert receipt.price_fact_version == 1
        assert initial_job.status == "COMPLETE"
        old_correction_id = initial_job.source_correction_id
        prior_outbox_id = await reader.scalar(select(func.max(OutboxEvent.id)))
        initial_cut = await reader.scalar(select(func.clock_timestamp()))

    # This is the only correction: no second FX write, synthetic event or manual rearm.
    correction_source = _price(2, "120")
    async with sessions() as writer:
        await ReferenceDataIngestionService(writer).append_authoritative_market_price_source_facts(
            [correction_source]
        )

    # A new session observes the committed ingress boundary and all existing work authorities.
    async with sessions() as reader:
        committed_cut = await reader.scalar(select(func.clock_timestamp()))
        accepted = await reader.scalar(
            select(MarketPriceSourceFactRecord).where(
                MarketPriceSourceFactRecord.tenant_id == TENANT,
                MarketPriceSourceFactRecord.legal_book_id == BOOK,
                MarketPriceSourceFactRecord.security_id == SECURITY,
                MarketPriceSourceFactRecord.price_date == DAY,
                MarketPriceSourceFactRecord.fact_version == 2,
            )
        )
        assert accepted is not None
        assert accepted.price == Decimal("120")
        assert accepted.source_content_hash == correction_source["source_content_hash"]
        fx = await reader.scalar(select(FxRate).where(FxRate.rate_date == DAY))
        assert fx.rate == Decimal("1"), "Price-only proof must retain the original FX"
        job = await reader.scalar(
            select(PortfolioValuationJob).where(
                PortfolioValuationJob.portfolio_id == PORTFOLIO,
                PortfolioValuationJob.security_id == SECURITY,
                PortfolioValuationJob.valuation_date == DAY,
                PortfolioValuationJob.epoch == 0,
            )
        )
        new_outbox = list(
            (
                await reader.scalars(
                    select(OutboxEvent).where(
                        OutboxEvent.id > prior_outbox_id,
                    )
                )
            ).all()
        )
        instrument_replay = list(
            (
                await reader.scalars(
                    select(InstrumentReprocessingState).where(
                        InstrumentReprocessingState.security_id == SECURITY,
                    )
                )
            ).all()
        )
        replay = list((await reader.scalars(select(ReprocessingJob))).all())
        print(
            "CORE788_PRICE_ONLY="
            + json.dumps(
                {
                    "initial_cut": initial_cut,
                    "committed_cut": committed_cut,
                    "authority": correction_source,
                    "initial_value": "1000",
                    "unchanged_fx": fx.rate,
                    "selected_vector": capture.vectors[0],
                    "job": {
                        "status": job.status,
                        "requeue_requested": job.requeue_requested,
                        "source_correction_id": job.source_correction_id,
                        "valuation_date": job.valuation_date,
                        "epoch": job.epoch,
                    },
                    "new_outbox": [
                        {
                            "id": row.id,
                            "event_type": row.event_type,
                            "payload": row.payload,
                        }
                        for row in new_outbox
                    ],
                    "instrument_replay": [
                        {
                            "security_id": row.security_id,
                            "earliest_impacted_date": row.earliest_impacted_date,
                        }
                        for row in instrument_replay
                    ],
                    "reprocessing_jobs": [
                        {
                            "job_type": row.job_type,
                            "status": row.status,
                            "payload": row.payload,
                        }
                        for row in replay
                    ],
                },
                default=str,
                sort_keys=True,
            )
        )
        # Only the real scoped source-owned event satisfies this authority's intent.
        # Unrelated FX and snapshot events cannot satisfy price correction durability.
        price_events = [
            row
            for row in new_outbox
            if (
                row.event_type == "AuthoritativeMarketPriceAuthorityChanged"
                and row.payload.get("security_id") == SECURITY
                and row.payload.get("price_date") == DAY.isoformat()
                and row.payload.get("tenant_id") == TENANT
                and row.payload.get("legal_book_id") == BOOK
            )
        ]
        rearmed = (
            job.status == "PENDING"
            and job.source_correction_id is not None
            and job.source_correction_id != old_correction_id
        )
        impacted = [row for row in instrument_replay if row.earliest_impacted_date <= DAY]
        price_replay = [
            row
            for row in replay
            if (
                row.job_type == "RESET_WATERMARKS"
                and row.status in {"PENDING", "PROCESSING"}
                and row.payload.get("security_id") == SECURITY
            )
        ]
        assert rearmed or price_events or impacted or price_replay, (
            "Authoritative price version2 committed for the exact tenant/book/security/date, "
            "but no production price correction outbox, rearmed job or bounded replay intent "
            "exists. Initial 1000 completion and unchanged FX1 do not authorize 1200 recovery."
        )
        assert len(price_events) == 1
        assert price_events[0].payload["accepted"]["fact_version"] == 2
        price_payload = price_events[0].payload
    await price_event_consumer.PriceEventConsumer(
        "unused:9092",
        "market_prices.persisted",
        CORRELATION,
    ).process_message(_message(price_payload, topic="market_prices.persisted", offset=2))
    # Duplicate and delayed initial intents cannot supply an older price.
    consumer = price_event_consumer.PriceEventConsumer(
        "unused:9092", "market_prices.persisted", CORRELATION
    )
    await consumer.process_message(
        _message(price_payload, topic="market_prices.persisted", offset=3)
    )
    async with sessions() as reader:
        initial_price_event = await reader.scalar(
            select(OutboxEvent)
            .where(OutboxEvent.event_type == "AuthoritativeMarketPriceAuthorityChanged")
            .order_by(OutboxEvent.id)
        )
        delayed_payload = initial_price_event.payload
    await consumer.process_message(
        _message(delayed_payload, topic="market_prices.persisted", offset=4)
    )
    fresh_token = await _claim(sessions)
    await build_valuation_job_processor(session_provider=session_provider).process_valid_event(
        event,
        "core788-price-only-corrected",
        CORRELATION,
        claim_token=fresh_token,
    )
    async with sessions() as reader:
        corrected = await reader.scalar(select(DailyPositionSnapshot))
        corrected_receipt = await reader.scalar(select(DailyPositionValuationReceiptRecord))
        assert corrected.market_value == Decimal("1200"), "Independent price-only 1200 oracle"
        assert corrected_receipt.price_fact_version == 2
