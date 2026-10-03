"""Registered API and PostgreSQL proof for cashflow portfolio-currency conversion."""

import json
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest
from portfolio_common.database_models import Cashflow, FxRate, Portfolio, Transaction
from portfolio_common.db import get_async_db_session
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.ingestion_service.app.dependencies import (
    get_ingestion_publish_command_handler,
    get_transaction_portfolio_ownership_validator,
)
from src.services.ingestion_service.app.main import app as ingestion_app
from src.services.ingestion_service.app.services.ingestion_publish_commands import (
    IngestionCommandResult,
)
from src.services.persistence_service.app.consumers import base_consumer as base_consumer_module
from src.services.persistence_service.app.consumers.transaction_consumer import (
    TransactionPersistenceConsumer,
)
from src.services.query_service.app.main import app as query_app
from tests.test_support.tenant import TEST_LEGAL_BOOK_ID, TEST_TENANT_HEADERS, TEST_TENANT_ID

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]

AS_OF_DATE = date(2026, 3, 27)
SETTLEMENT_DATE = date(2026, 3, 28)


def _portfolio(portfolio_id: str) -> Portfolio:
    return Portfolio(
        portfolio_id=portfolio_id,
        tenant_id=TEST_TENANT_ID,
        legal_book_id=TEST_LEGAL_BOOK_ID,
        base_currency="USD",
        open_date=date(2026, 1, 1),
        risk_exposure="MODERATE",
        investment_time_horizon="MEDIUM_TERM",
        portfolio_type="DISCRETIONARY",
        objective="CAPITAL_GROWTH",
        booking_center_code="SG",
        client_id=f"CLIENT-{portfolio_id}",
        status="ACTIVE",
        is_leverage_allowed=False,
    )


def _transaction(
    *,
    transaction_id: str,
    portfolio_id: str,
    currency: str,
    amount: Decimal,
    transaction_type: str,
    settlement_date: date | None,
) -> Transaction:
    return Transaction(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        instrument_id=f"CASH_{currency}",
        security_id=f"CASH_{currency}",
        transaction_type=transaction_type,
        quantity=Decimal("1"),
        price=abs(amount),
        gross_transaction_amount=abs(amount),
        trade_currency=currency,
        currency=currency,
        transaction_date=datetime(2026, 3, 26, tzinfo=UTC),
        settlement_date=(
            datetime.combine(settlement_date, datetime.min.time(), tzinfo=UTC)
            if settlement_date
            else None
        ),
    )


async def _seed_projection_cases(session: AsyncSession) -> None:
    cases = (
        ("CF-FX-USD", "USD"),
        ("CF-FX-EUR", "EUR"),
        ("CF-FX-GBP-MISSING", "GBP"),
        ("CF-FX-OVERLAP", "USD"),
    )
    for portfolio_id, currency in cases:
        session.add(_portfolio(portfolio_id))
        booked_transaction_id = f"{portfolio_id}-BOOKED"
        session.add(
            _transaction(
                transaction_id=booked_transaction_id,
                portfolio_id=portfolio_id,
                currency=currency,
                amount=Decimal("100"),
                transaction_type="BUY",
                settlement_date=None,
            )
        )
        session.add(
            Cashflow(
                transaction_id=booked_transaction_id,
                portfolio_id=portfolio_id,
                security_id=f"CASH_{currency}",
                cashflow_date=AS_OF_DATE,
                amount=Decimal("100"),
                currency=currency,
                classification="CASHFLOW_IN",
                timing="EOD",
                calculation_type="NET",
                is_portfolio_flow=True,
                epoch=0,
            )
        )

    for portfolio_id, currency in cases[:3]:
        session.add(
            _transaction(
                transaction_id=f"{portfolio_id}-PROJECTED",
                portfolio_id=portfolio_id,
                currency=currency,
                amount=Decimal("25"),
                transaction_type="WITHDRAWAL",
                settlement_date=SETTLEMENT_DATE,
            )
        )

    overlap_transaction_id = "CF-FX-OVERLAP-SETTLEMENT"
    session.add(
        _transaction(
            transaction_id=overlap_transaction_id,
            portfolio_id="CF-FX-OVERLAP",
            currency="USD",
            amount=Decimal("40"),
            transaction_type="DEPOSIT",
            settlement_date=SETTLEMENT_DATE,
        )
    )
    session.add(
        Cashflow(
            transaction_id=overlap_transaction_id,
            portfolio_id="CF-FX-OVERLAP",
            security_id="CASH_USD",
            cashflow_date=SETTLEMENT_DATE,
            amount=Decimal("40"),
            currency="USD",
            classification="CASHFLOW_IN",
            timing="EOD",
            calculation_type="NET",
            is_portfolio_flow=True,
            epoch=0,
        )
    )
    session.add_all(
        [
            FxRate(
                from_currency="EUR",
                to_currency="USD",
                rate_date=AS_OF_DATE,
                rate=Decimal("2"),
            ),
            FxRate(
                from_currency="EUR",
                to_currency="USD",
                rate_date=SETTLEMENT_DATE,
                rate=Decimal("2"),
            ),
            FxRate(
                from_currency="GBP",
                to_currency="USD",
                rate_date=date(2026, 3, 26),
                rate=Decimal("1.25"),
            ),
            FxRate(
                from_currency="USD",
                to_currency="GBP",
                rate_date=AS_OF_DATE,
                rate=Decimal("0.8"),
            ),
        ]
    )
    await session.commit()


async def _request(client: httpx.AsyncClient, portfolio_id: str, **headers: str):
    return await client.get(
        f"/portfolios/{portfolio_id}/cashflow-projection",
        params={"as_of_date": AS_OF_DATE.isoformat(), "horizon_days": 1},
        headers=headers or TEST_TENANT_HEADERS,
    )


class _CapturedPublishHandler:
    def __init__(self) -> None:
        self.payload: dict[str, object] | None = None

    async def ingest_transaction(self, command) -> IngestionCommandResult:
        self.payload = command.record.model_dump(mode="json")
        return IngestionCommandResult(
            message=command.accepted_message,
            entity_type=command.entity_type,
            accepted_count=1,
            idempotency_key=command.idempotency_key,
        )


class _AdmittedPortfolioValidator:
    async def validate(self, **_kwargs: object) -> None:
        return None


class _FakeKafkaMessage:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def topic(self) -> str:
        return "raw-transactions"

    def partition(self) -> int:
        return 0

    def offset(self) -> int:
        return 1

    def value(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def key(self) -> bytes:
        return str(self._payload["transaction_id"]).encode("utf-8")

    def headers(self):
        return [("correlation_id", b"CID-CASHFLOW-FX-INGRESS")]


async def test_cashflow_projection_converts_before_aggregation_and_binds_fx_evidence(
    clean_db,
    async_db_session: AsyncSession,
) -> None:
    await _seed_projection_cases(async_db_session)

    async def database_session():
        yield async_db_session

    assert get_async_db_session not in query_app.dependency_overrides
    query_app.dependency_overrides[get_async_db_session] = database_session
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=query_app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            usd = await _request(client, "CF-FX-USD")
            await async_db_session.rollback()
            eur = await _request(client, "CF-FX-EUR")
            await async_db_session.rollback()
            eur_replay = await _request(client, "CF-FX-EUR")
            await async_db_session.rollback()
            missing = await _request(client, "CF-FX-GBP-MISSING")
            await async_db_session.rollback()
            overlap = await _request(client, "CF-FX-OVERLAP")
            await async_db_session.rollback()
            foreign = await _request(
                client,
                "CF-FX-EUR",
                **{"X-Tenant-Id": "tenant-foreign"},
            )
            await async_db_session.rollback()

            original_eur = eur.json()
            await async_db_session.execute(
                update(FxRate)
                .where(
                    FxRate.from_currency == "EUR",
                    FxRate.to_currency == "USD",
                    FxRate.rate_date == AS_OF_DATE,
                )
                .values(rate=Decimal("3"))
            )
            await async_db_session.commit()
            corrected = await _request(client, "CF-FX-EUR")
            await async_db_session.rollback()
    finally:
        query_app.dependency_overrides.pop(get_async_db_session)

    assert usd.status_code == 200, usd.text
    usd_payload = usd.json()
    assert Decimal(str(usd_payload["booked_total_net_cashflow"])) == Decimal("100")
    assert Decimal(str(usd_payload["projected_settlement_total_cashflow"])) == Decimal("-25")
    assert Decimal(str(usd_payload["total_net_cashflow"])) == Decimal("75")

    assert eur.status_code == 200, eur.text
    assert Decimal(str(original_eur["booked_total_net_cashflow"])) == Decimal("200")
    assert Decimal(str(original_eur["projected_settlement_total_cashflow"])) == Decimal("-50")
    assert Decimal(str(original_eur["total_net_cashflow"])) == Decimal("150")
    assert original_eur["portfolio_currency"] == "USD"
    assert original_eur["data_quality_status"] == "COMPLETE"
    assert eur_replay.status_code == 200, eur_replay.text
    replay_payload = eur_replay.json()
    assert replay_payload["source_cut_id"] == original_eur["source_cut_id"]
    assert replay_payload["request_fingerprint"] == original_eur["request_fingerprint"]
    assert replay_payload["snapshot_id"] == original_eur["snapshot_id"]
    assert replay_payload["content_hash"] == original_eur["content_hash"]

    assert missing.status_code == 400, missing.text
    assert "exact-date direct FX conversion evidence" in missing.json()["detail"]
    assert overlap.status_code == 200, overlap.text
    assert Decimal(str(overlap.json()["booked_total_net_cashflow"])) == Decimal("140")
    assert Decimal(str(overlap.json()["projected_settlement_total_cashflow"])) == Decimal("0")
    assert foreign.status_code == 404, foreign.text

    assert corrected.status_code == 200, corrected.text
    corrected_payload = corrected.json()
    assert Decimal(str(corrected_payload["booked_total_net_cashflow"])) == Decimal("300")
    assert Decimal(str(corrected_payload["projected_settlement_total_cashflow"])) == Decimal("-50")
    assert corrected_payload["source_cut_id"] == original_eur["source_cut_id"]
    assert corrected_payload["request_fingerprint"] != original_eur["request_fingerprint"]
    assert corrected_payload["snapshot_id"] != original_eur["snapshot_id"]
    assert corrected_payload["content_hash"] != original_eur["content_hash"]


async def test_supported_transaction_ingress_reaches_converted_projection(
    clean_db,
    async_db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    portfolio_id = "CF-FX-SUPPORTED-INGRESS"
    async_db_session.add(_portfolio(portfolio_id))
    async_db_session.add(
        FxRate(
            from_currency="EUR",
            to_currency="USD",
            rate_date=SETTLEMENT_DATE,
            rate=Decimal("2"),
        )
    )
    await async_db_session.commit()

    captured_handler = _CapturedPublishHandler()
    ingestion_app.dependency_overrides[get_ingestion_publish_command_handler] = lambda: (
        captured_handler
    )
    ingestion_app.dependency_overrides[get_transaction_portfolio_ownership_validator] = (
        _AdmittedPortfolioValidator
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=ingestion_app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            accepted = await client.post(
                "/ingest/transaction",
                headers=TEST_TENANT_HEADERS,
                json={
                    "transaction_id": "CF-FX-SUPPORTED-INGRESS-TXN",
                    "portfolio_id": portfolio_id,
                    "instrument_id": "CASH_EUR",
                    "security_id": "CASH_EUR",
                    "transaction_date": "2026-03-26T00:00:00Z",
                    "settlement_date": "2026-03-28T00:00:00Z",
                    "transaction_type": "WITHDRAWAL",
                    "quantity": "1",
                    "price": "25",
                    "gross_transaction_amount": "25",
                    "trade_currency": "EUR",
                    "currency": "EUR",
                    "source_system": "CORE_BANKING_ADAPTER",
                },
            )
    finally:
        ingestion_app.dependency_overrides.pop(get_ingestion_publish_command_handler)
        ingestion_app.dependency_overrides.pop(get_transaction_portfolio_ownership_validator)

    assert accepted.status_code == 202, accepted.text
    assert captured_handler.payload is not None
    async_factory = async_sessionmaker(async_db_session.bind, expire_on_commit=False)

    async def current_test_session() -> AsyncIterator[AsyncSession]:
        async with async_factory() as session:
            yield session

    monkeypatch.setattr(base_consumer_module, "get_async_db_session", current_test_session)
    consumer = TransactionPersistenceConsumer(
        bootstrap_servers="unused-in-db-direct-proof:9092",
        topic="raw-transactions",
        group_id="cashflow-fx-supported-ingress",
        dlq_topic=None,
    )
    await consumer.process_message(_FakeKafkaMessage(captured_handler.payload))

    async def database_session():
        yield async_db_session

    query_app.dependency_overrides[get_async_db_session] = database_session
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=query_app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await _request(client, portfolio_id)
            await async_db_session.rollback()
    finally:
        query_app.dependency_overrides.pop(get_async_db_session)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert Decimal(str(payload["booked_total_net_cashflow"])) == Decimal("0")
    assert Decimal(str(payload["projected_settlement_total_cashflow"])) == Decimal("-50")
    assert Decimal(str(payload["total_net_cashflow"])) == Decimal("-50")
    assert payload["portfolio_currency"] == "USD"
