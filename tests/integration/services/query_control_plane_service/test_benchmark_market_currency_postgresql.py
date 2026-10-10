"""Registered market-window currency authority on the owned PostgreSQL test database."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from portfolio_common.database_models import (
    BenchmarkCompositionSeries,
    BenchmarkDefinition,
    FxRate,
    IndexPriceSeries,
)
from portfolio_common.db import get_async_db_session
from sqlalchemy import event

from src.services.query_control_plane_service.app.main import app
from tests.test_support.fx_source_fixtures import signed_headers

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]
AS_OF = date(2024, 2, 29)
OBSERVED = datetime(2024, 2, 29, 16, tzinfo=UTC)
PRICE = Decimal("42.1234567890")
RATE = Decimal("1.3500000001")


@pytest_asyncio.fixture
async def market_window(async_db_session, monkeypatch):
    """Use real source adapters; roll back this test's rows when its session closes."""

    monkeypatch.setenv("ENTERPRISE_ENFORCE_AUTHZ", "false")
    monkeypatch.setenv("ENTERPRISE_PRIMARY_KEY_ID", "synthetic-http-key")
    monkeypatch.setenv(
        "ENTERPRISE_AUTH_CONTEXT_HMAC_SECRET", "synthetic-http-proof-secret-32-bytes"
    )

    async def session_override():
        yield async_db_session

    monkeypatch.setitem(app.dependency_overrides, get_async_db_session, session_override)
    statements = []

    def record_select(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement.lower())

    engine = async_db_session.bind.sync_engine
    event.listen(engine, "before_cursor_execute", record_select)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield async_db_session, client, statements
    finally:
        event.remove(engine, "before_cursor_execute", record_select)


async def seed_sources(session, *, definition_state):
    benchmark_id, index_id = "SYNTHETIC_BMK_" + uuid4().hex, "SYNTHETIC_IDX_" + uuid4().hex
    if definition_state != "missing":
        session.add(
            BenchmarkDefinition(
                benchmark_id=benchmark_id,
                benchmark_name="Synthetic currency authority control",
                benchmark_type="CUSTOM",
                benchmark_currency="USD",
                return_convention="TOTAL_RETURN",
                effective_from=date(2024, 3, 1)
                if definition_state == "future"
                else date(2024, 1, 1),
                effective_to=date(2024, 2, 28) if definition_state == "expired" else None,
                quality_status="ACCEPTED",
                source_timestamp=OBSERVED,
            )
        )
    session.add_all(
        [
            BenchmarkCompositionSeries(
                benchmark_id=benchmark_id,
                index_id=index_id,
                composition_effective_from=date(2024, 1, 1),
                composition_weight=Decimal("1"),
                quality_status="ACCEPTED",
                source_timestamp=OBSERVED,
            ),
            IndexPriceSeries(
                series_id=index_id,
                index_id=index_id,
                series_date=AS_OF,
                index_price=PRICE,
                series_currency="USD",
                value_convention="CLOSE",
                quality_status="ACCEPTED",
                source_timestamp=OBSERVED,
            ),
        ]
    )
    await session.flush()
    return benchmark_id


def request_body(target_currency):
    return {
        "as_of_date": AS_OF.isoformat(),
        "frequency": "daily",
        "window": {"start_date": AS_OF.isoformat(), "end_date": AS_OF.isoformat()},
        "target_currency": target_currency,
        "series_fields": ["index_price", "fx_rate"] if target_currency else ["index_price"],
    }


async def post_window(client, benchmark_id, body):
    return await client.post(
        f"/integration/benchmarks/{benchmark_id}/market-series",
        json=body,
        headers=signed_headers(capability="source_data.market_data_window.read"),
    )


@pytest.mark.parametrize("definition_state", ["missing", "future", "expired"])
@pytest.mark.parametrize("target_currency", [None, "USD", "SGD"])
async def test_unavailable_definition_refuses_without_downstream_reads(
    market_window, definition_state, target_currency
):
    session, client, statements = market_window
    benchmark_id = await seed_sources(session, definition_state=definition_state)
    response = await post_window(client, benchmark_id, request_body(target_currency))
    assert response.status_code == 409, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["error_code"] == "QCP_FX_SOURCE_SELECTION_CONFLICT"
    schema = (await client.get("/openapi.json")).json()
    example = schema["paths"]["/integration/benchmarks/{benchmark_id}/market-series"]["post"][
        "responses"
    ]["409"]["content"]["application/problem+json"]["example"]
    for field in ("type", "title", "status", "detail", "error_code"):
        assert response.json()[field] == example[field]
    assert response.json()["metadata"] == {
        "source_product": "MarketDataWindow",
        "benchmark_id": benchmark_id,
    }
    assert len(statements) == 1
    assert "benchmark_definitions" in statements[0]
    assert "benchmark_currency" not in response.json()
    assert "component_series" not in response.json()


@pytest.mark.parametrize("target_currency", [None, "USD", "SGD"])
async def test_effective_definition_preserves_exact_native_price_and_fx_context(
    market_window, target_currency
):
    session, client, _ = market_window
    benchmark_id = await seed_sources(session, definition_state="effective")
    if target_currency == "SGD":
        session.add(FxRate(from_currency="USD", to_currency="SGD", rate_date=AS_OF, rate=RATE))
        await session.flush()
    response = await post_window(client, benchmark_id, request_body(target_currency))
    assert response.status_code == 200, response.text
    result = response.json()
    point = result["component_series"][0]["points"][0]
    assert result["benchmark_currency"] == "USD"
    assert result["fx_context_source_currency"] == ("USD" if target_currency else None)
    assert result["fx_context_target_currency"] == target_currency
    assert point["series_currency"] == "USD"
    assert Decimal(point["index_price"]) == PRICE
    if target_currency:
        assert Decimal(point["fx_rate"]) == (Decimal("1") if target_currency == "USD" else RATE)
    else:
        assert point["fx_rate"] is None
    assert result["fx_source_qualification"] == (
        "NOT_REQUESTED"
        if target_currency is None
        else "IDENTITY"
        if target_currency == "USD"
        else "LEGACY_UNQUALIFIED"
    )
    assert result["product_name"] == "MarketDataWindow"
    assert result["source_lineage"]["source_owner"] == "lotus-core"
    assert (
        result["normalization_policy"]
        == "native_component_series_downstream_normalization_required"
    )


async def test_explicit_retained_selection_still_refuses_missing_definition(market_window):
    session, client, statements = market_window
    benchmark_id = await seed_sources(session, definition_state="missing")
    body = request_body("SGD")
    body["fx_source"] = {
        "provider_id": "SYNTHETIC_PROVIDER",
        "source_id": "SYNTHETIC_FEED",
        "source_as_of": OBSERVED.isoformat(),
        "known_as_of": OBSERVED.isoformat(),
    }
    response = await post_window(client, benchmark_id, body)
    assert response.status_code == 409, response.text
    assert response.json()["error_code"] == "QCP_FX_SOURCE_SELECTION_CONFLICT"
    assert len(statements) == 1
    assert "benchmark_definitions" in statements[0]
