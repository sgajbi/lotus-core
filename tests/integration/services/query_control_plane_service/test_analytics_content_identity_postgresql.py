"""Actual PostgreSQL source corrections must reach both HTTP content identities."""

import gzip
import json
import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from portfolio_common import db as database_provider
from portfolio_common.database_models import (
    AnalyticsExportJob,
    BusinessDate,
    Cashflow,
    FxRate,
    Instrument,
    Portfolio,
    PositionHistory,
    PositionState,
    PositionTimeseries,
    Transaction,
)
from portfolio_common.domain.tenant import TenantId
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.query_control_plane_service.app.application.analytics import (
    analytics_export_execution,
)
from src.services.query_control_plane_service.app.application.analytics.analytics_timeseries_service import (  # noqa: E501
    AnalyticsRuntimePolicy,
    AnalyticsTimeseriesService,
)
from src.services.query_control_plane_service.app.dependencies import (
    get_analytics_timeseries_service,
)
from src.services.query_control_plane_service.app.enterprise_readiness import (
    build_enterprise_audit_middleware,
)
from src.services.query_control_plane_service.app.exception_mappers import (
    register_query_control_plane_exception_handlers,
)
from src.services.query_control_plane_service.app.infrastructure.analytics_export_repository import (  # noqa: E501
    AnalyticsExportRepository,
)
from src.services.query_control_plane_service.app.infrastructure.analytics_timeseries_repository import (  # noqa: E501
    AnalyticsTimeseriesRepository,
)
from src.services.query_control_plane_service.app.infrastructure.analytics_unit_of_work import (  # noqa: E501
    SqlAlchemyAnalyticsUnitOfWork,
)
from src.services.query_control_plane_service.app.routers.analytics_inputs import router

pytestmark = [pytest.mark.asyncio, pytest.mark.db_direct, pytest.mark.lifecycle]
PORTFOLIO_ID = "CONTENT_IDENTITY_PG"
SECURITY_ID = "CONTENT_IDENTITY_EQUITY"
TRANSACTION_ID = "CONTENT_IDENTITY_FLOW"
FIRST_DAY = date(2026, 4, 10)
LAST_DAY = date(2026, 4, 13)


@pytest_asyncio.fixture
async def content_identity_client(clean_db, async_db_session, monkeypatch):
    """Own only the HTTP client; borrow the governed fixture's PostgreSQL session."""

    serving_clock = MagicMock(wraps=datetime)
    serving_clock.now.side_effect = [
        datetime(2026, 10, 8, 1, 0, second, tzinfo=UTC) for second in range(10)
    ]
    monkeypatch.setattr(
        "src.services.query_control_plane_service.app.application.analytics."
        "analytics_timeseries_service.datetime",
        serving_clock,
    )
    session = async_db_session
    # The governed financial-table cleanup does not include durable export jobs.
    # Isolate only this suite's named portfolio; preserve all other retained jobs.
    await session.execute(
        delete(AnalyticsExportJob).where(AnalyticsExportJob.portfolio_id == PORTFOLIO_ID)
    )
    session.add(
        Portfolio(
            tenant_id="tenant-content-identity",
            portfolio_id=PORTFOLIO_ID,
            base_currency="USD",
            open_date=FIRST_DAY,
            risk_exposure="moderate",
            investment_time_horizon="long_term",
            portfolio_type="discretionary",
            booking_center_code="Singapore",
            client_id="CLIENT_CONTENT_IDENTITY",
            status="ACTIVE",
        )
    )
    session.add(
        Instrument(
            security_id=SECURITY_ID,
            name="Content identity equity",
            isin="CONTENT-IDENTITY-PG",
            currency="USD",
            product_type="EQUITY",
            asset_class="Equity",
        )
    )
    session.add_all(BusinessDate(date=day) for day in (FIRST_DAY, LAST_DAY))
    await session.flush()
    session.add(
        Transaction(
            transaction_id=TRANSACTION_ID,
            portfolio_id=PORTFOLIO_ID,
            instrument_id=SECURITY_ID,
            security_id=SECURITY_ID,
            transaction_date=datetime(2026, 4, 10, 9, tzinfo=UTC),
            settlement_date=datetime(2026, 4, 10, 16, tzinfo=UTC),
            transaction_type="BUY",
            quantity=Decimal("10"),
            price=Decimal("10"),
            gross_transaction_amount=Decimal("100"),
            trade_currency="USD",
            currency="USD",
        )
    )
    await session.flush()
    session.add(
        PositionState(
            portfolio_id=PORTFOLIO_ID,
            security_id=SECURITY_ID,
            epoch=1,
            watermark_date=LAST_DAY,
            status="CURRENT",
        )
    )
    for day, beginning, ending in ((FIRST_DAY, "100", "110"), (LAST_DAY, "110", "120")):
        session.add(
            PositionHistory(
                portfolio_id=PORTFOLIO_ID,
                security_id=SECURITY_ID,
                transaction_id=TRANSACTION_ID,
                position_date=day,
                epoch=1,
                quantity=Decimal("10"),
                cost_basis=Decimal("100"),
                cost_basis_local=Decimal("100"),
            )
        )
        session.add(
            PositionTimeseries(
                portfolio_id=PORTFOLIO_ID,
                security_id=SECURITY_ID,
                date=day,
                epoch=1,
                bod_market_value=Decimal(beginning),
                eod_market_value=Decimal(ending),
                bod_cashflow_position=Decimal("0"),
                eod_cashflow_position=Decimal("0"),
                bod_cashflow_portfolio=Decimal("0"),
                eod_cashflow_portfolio=Decimal("0"),
                fees=Decimal("0"),
                quantity=Decimal("10"),
                cost=Decimal("100"),
            )
        )
        session.add(
            FxRate(from_currency="USD", to_currency="SGD", rate_date=day, rate=Decimal("2"))
        )
    session.add(
        Cashflow(
            transaction_id=TRANSACTION_ID,
            portfolio_id=PORTFOLIO_ID,
            security_id=SECURITY_ID,
            cashflow_date=FIRST_DAY,
            epoch=1,
            amount=Decimal("5"),
            currency="USD",
            classification="CASHFLOW_IN",
            timing="EOD",
            calculation_type="SOURCE",
            is_position_flow=True,
            is_portfolio_flow=True,
        )
    )
    await session.commit()
    service = export_service(session)
    app = export_app(service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client, session


def export_service(session):
    return AnalyticsTimeseriesService(
        reader=AnalyticsTimeseriesRepository(
            session, tenant_id=TenantId("tenant-content-identity")
        ),
        export_store=AnalyticsExportRepository(session),
        unit_of_work=SqlAlchemyAnalyticsUnitOfWork(session),
        policy=AnalyticsRuntimePolicy(
            page_token_secret="content-identity-test-key",
            page_token_key_id="k1",
            page_token_previous_keys={},
            page_token_ttl_seconds=900,
            export_stale_timeout_minutes=15,
            export_execution_timeout_seconds=300,
        ),
    )


def export_app(service):
    app = FastAPI()
    app.include_router(router)
    register_query_control_plane_exception_handlers(app, logger=logging.getLogger(__name__))
    if service is None:
        # Every real composition-root acquisition requires canonical admission.
        app.middleware("http")(build_enterprise_audit_middleware())
    else:
        app.dependency_overrides[get_analytics_timeseries_service] = lambda: service
    return app


async def read_page(client, dataset, **page):
    return await client.post(
        f"/integration/portfolios/{PORTFOLIO_ID}/analytics/{dataset}-timeseries",
        headers={"X-Tenant-Id": "tenant-content-identity"},
        json={
            "as_of_date": LAST_DAY.isoformat(),
            "window": {"start_date": FIRST_DAY.isoformat(), "end_date": LAST_DAY.isoformat()},
            "reporting_currency": "SGD",
            "page": {"page_size": 10, **page},
        },
    )


@pytest.mark.parametrize("dataset", ["portfolio", "position"])
async def test_analytics_acquisition_keeps_pre_mutation_fx_snapshot(
    content_identity_client, dataset, monkeypatch
):
    """A committed writer between epoch and FX reads must not mix one HTTP acquisition."""
    _, seed_session = content_identity_client
    session_factory = async_sessionmaker(bind=seed_session.bind, expire_on_commit=False)
    monkeypatch.setattr(database_provider, "AsyncSessionLocal", session_factory)
    original_epoch = AnalyticsTimeseriesRepository.get_position_snapshot_epoch
    mutation_committed = False

    async def epoch_then_commit_correction(self, **kwargs):
        nonlocal mutation_committed
        epoch = await original_epoch(self, **kwargs)
        if not mutation_committed:
            async with session_factory() as writer:
                await writer.execute(
                    update(FxRate)
                    .where(FxRate.from_currency == "USD", FxRate.to_currency == "SGD")
                    .values(rate=Decimal("4"))
                )
                await writer.commit()
            mutation_committed = True
        return epoch

    monkeypatch.setattr(
        AnalyticsTimeseriesRepository, "get_position_snapshot_epoch", epoch_then_commit_correction
    )
    app = export_app(None)
    # Exercise the actual composition root, not the fixture's injected reader/export service.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await read_page(client, dataset)
    assert mutation_committed, "Writer must commit while the reader transaction remains open"
    assert response.status_code == 200, response.text
    assert ending_value(economic_rows(response.json(), dataset)[0], dataset) == Decimal("220")
    # A later request must acquire the new committed value, not reuse an old reader snapshot.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        corrected = await read_page(client, dataset)
    assert corrected.status_code == 200, corrected.text
    assert ending_value(economic_rows(corrected.json(), dataset)[0], dataset) == Decimal("440")


@pytest.mark.parametrize("dataset", ["portfolio", "position"])
@pytest.mark.parametrize("correction", ["fx", "valuation"])
async def test_actual_http_continuation_refuses_prior_page_same_epoch_correction(
    content_identity_client, dataset, correction, monkeypatch
):
    _, session = content_identity_client
    monkeypatch.setattr(
        database_provider,
        "AsyncSessionLocal",
        async_sessionmaker(bind=session.bind, expire_on_commit=False),
    )
    app = export_app(None)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        first = await read_page(client, dataset, page_size=1)
        assert first.status_code == 200, first.text
        token = first.json()["page"]["next_page_token"]
        assert token is not None
        unchanged = await read_page(client, dataset, page_size=1, page_token=token)
        assert unchanged.status_code == 200, unchanged.text
        assert ending_value(economic_rows(unchanged.json(), dataset)[0], dataset) == Decimal("240")
        if correction == "fx":
            await session.execute(
                update(FxRate)
                .where(
                    FxRate.from_currency == "USD",
                    FxRate.to_currency == "SGD",
                    FxRate.rate_date == FIRST_DAY,
                )
                .values(rate=Decimal("3"))
            )
        else:
            await session.execute(
                update(PositionTimeseries)
                .where(
                    PositionTimeseries.portfolio_id == PORTFOLIO_ID,
                    PositionTimeseries.security_id == SECURITY_ID,
                    PositionTimeseries.date == FIRST_DAY,
                )
                .values(eod_market_value=Decimal("115"))
            )
        await session.commit()
        stale = await read_page(client, dataset, page_size=1, page_token=token)
    assert stale.status_code == 409, stale.text
    assert stale.json()["error_code"] == "QCP_ANALYTICS_STALE_CONTINUATION"
    assert "rows" not in stale.json() and "observations" not in stale.json()


@pytest.mark.parametrize("dataset", ["portfolio", "position"])
@pytest.mark.parametrize(
    "source_case", ["consistent", "degraded", "degraded_first", "mixed", "unknown", "empty"]
)
async def test_export_retained_page_evidence_pg_http(
    content_identity_client, dataset, source_case, monkeypatch
):
    """Real source rows, job storage and HTTP; controlled source metadata, not cut certification."""
    client, session = content_identity_client
    method_name = f"get_{dataset}_timeseries"
    original_get = getattr(AnalyticsTimeseriesService, method_name)
    acquired_pages = []

    async def observed_get(self, **kwargs):
        response = await original_get(self, **kwargs)
        second = bool(acquired_pages)
        # Only the evidence-policy inputs are controlled. Economics come from actual PostgreSQL.
        updates = {
            "source_cut_id": "cut-B" if second and source_case == "mixed" else "cut-A",
            "data_quality_status": "COMPLETE",
            "freshness_status": "CURRENT",
            "source_evidence_current": True,
        }
        if (second and source_case == "degraded") or (
            not second and source_case == "degraded_first"
        ):
            updates.update(
                data_quality_status="PARTIAL",
                freshness_status="STALE",
                source_evidence_current=False,
            )
        if source_case == "unknown":
            updates["source_cut_id"] = None
        if source_case == "empty":
            updates["observations" if dataset == "portfolio" else "rows"] = []
            updates["page"] = response.page.model_copy(update={"returned_row_count": 0})
        response = response.model_copy(update=updates)
        acquired_pages.append(response.model_dump(mode="json"))
        return response

    monkeypatch.setattr(AnalyticsTimeseriesService, method_name, observed_get)
    monkeypatch.setattr(analytics_export_execution, "PORTFOLIO_EXPORT_PAGE_SIZE", 1)
    monkeypatch.setattr(analytics_export_execution, "POSITION_EXPORT_PAGE_SIZE", 1)
    created = await client.post(
        "/integration/exports/analytics-timeseries/jobs",
        json={
            "dataset_type": f"{dataset}_timeseries",
            "portfolio_id": PORTFOLIO_ID,
            f"{dataset}_timeseries_request": {
                "as_of_date": LAST_DAY.isoformat(),
                "window": {"start_date": FIRST_DAY.isoformat(), "end_date": LAST_DAY.isoformat()},
                "reporting_currency": "SGD",
            },
        },
    )
    assert created.status_code == 200, created.text
    job = created.json()
    job_id = job["job_id"]
    status_response = await client.get(f"/integration/exports/analytics-timeseries/jobs/{job_id}")
    assert status_response.status_code == 200, status_response.text
    stored = await AnalyticsExportRepository(session).get_job(job_id)
    assert stored is not None
    if source_case == "mixed":
        assert job["status"] == status_response.json()["status"] == "failed"
        assert stored.result_payload is None
        assert "source cuts" in job["error_message"]
        refused = await client.get(job["result_endpoint"])
        assert refused.status_code == 422, refused.text
        return
    assert job["status"] == status_response.json()["status"] == "completed"
    stored_payload = json.loads(json.dumps(stored.result_payload))
    expected_rows = [row for page in acquired_pages for row in economic_rows(page, dataset)]
    evidence = stored_payload["source_evidence"]
    assert len(acquired_pages) == 2
    # Rehydrate through a fresh borrowed-engine session and service/client instance.
    async with AsyncSession(bind=session.bind) as rehydrated_session:
        restarted_app = export_app(export_service(rehydrated_session))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=restarted_app), base_url="http://testserver"
        ) as restarted_client:
            reloaded = await restarted_client.get(job["result_endpoint"])
            assert reloaded.status_code == 200, reloaded.text
            assert reloaded.json()["source_evidence"] == evidence
            assert reloaded.json()["data"] == expected_rows
    assert len(acquired_pages) == 2
    assert stored_payload["data"] == expected_rows
    assert evidence["source_cut_id"] == (None if source_case == "unknown" else "cut-A")
    assert evidence["source_cut_status"] == (
        "UNAVAILABLE" if source_case == "unknown" else "AVAILABLE"
    )
    assert evidence["source_evidence_current"] is (
        source_case not in {"degraded", "degraded_first"}
    )
    if source_case == "degraded_first":
        assert evidence["quality_statuses"] == ["PARTIAL", "COMPLETE"]
        assert evidence["freshness_statuses"] == ["STALE", "CURRENT"]
        assert "PAGE_SOURCE_EVIDENCE_NOT_CURRENT" in evidence["unavailable_reasons"]
    assert len(evidence["pages"]) == 2
    for captured, page in zip(acquired_pages, evidence["pages"], strict=True):
        assert page["source_metadata"] == {
            key: value for key, value in captured.items() if key not in {"observations", "rows"}
        }
    # Actual later source correction must not rewrite a retained job result.
    await session.execute(
        update(PositionTimeseries)
        .where(PositionTimeseries.portfolio_id == PORTFOLIO_ID)
        .values(eod_market_value=Decimal("999"))
    )
    await session.commit()
    for _ in range(2):
        result = await client.get(job["result_endpoint"])
        ndjson = await client.get(job["result_endpoint"], params={"result_format": "ndjson"})
        assert result.status_code == ndjson.status_code == 200
        assert result.json()["data"] == expected_rows
        assert result.json()["source_evidence"] == evidence
        lines = [json.loads(line) for line in ndjson.content.splitlines()]
        assert lines[0]["source_evidence"] == evidence
        assert [line["record"] for line in lines[1:]] == expected_rows
    assert len(acquired_pages) == 2


@pytest.mark.parametrize("dataset", ["portfolio", "position"])
async def test_export_correction_intent_preserves_original_pg_http(
    content_identity_client, dataset
):
    """Real durable correction; not supported ingestion or provider qualification."""
    client, session = content_identity_client
    endpoint = "/integration/exports/analytics-timeseries/jobs"
    request = {
        "dataset_type": f"{dataset}_timeseries",
        "portfolio_id": PORTFOLIO_ID,
        f"{dataset}_timeseries_request": {
            "as_of_date": LAST_DAY.isoformat(),
            "window": {"start_date": FIRST_DAY.isoformat(), "end_date": LAST_DAY.isoformat()},
            "reporting_currency": "SGD",
        },
    }
    original = await client.post(endpoint, json=request)
    assert original.status_code == 200, original.text
    assert original.json()["status"] == "completed"
    original_result = await client.get(original.json()["result_endpoint"])
    assert original_result.status_code == 200
    retained = original_result.json()
    await session.execute(
        update(PositionTimeseries)
        .where(PositionTimeseries.portfolio_id == PORTFOLIO_ID, PositionTimeseries.date == LAST_DAY)
        .values(eod_market_value=Decimal("125"))
    )
    await session.commit()
    replay = await client.post(endpoint, json=request)
    assert replay.json()["job_id"] == original.json()["job_id"]
    correction = {**request, "refresh_of_job_id": original.json()["job_id"]}
    refreshed = await client.post(endpoint, json=correction)
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["status"] == "completed"
    assert refreshed.json()["job_id"] != original.json()["job_id"]
    retry = await client.post(endpoint, json=correction)
    assert retry.json()["job_id"] == refreshed.json()["job_id"]
    result = await client.get(refreshed.json()["result_endpoint"])
    assert result.status_code == 200
    corrected = result.json()
    assert ending_value(retained["data"][-1], dataset) == Decimal("240")
    assert ending_value(corrected["data"][-1], dataset) == Decimal("250")
    assert (
        retained["source_evidence"]["selection_digest"]
        != corrected["source_evidence"]["selection_digest"]
    )
    assert corrected["source_evidence"]["source_cut_status"] == "UNAVAILABLE"
    assert corrected["source_evidence"]["source_cut_id"] is None
    await session.rollback()  # End result-read autobegin before fresh-session rehydration.
    async with AsyncSession(bind=session.bind) as fresh_session:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=export_app(export_service(fresh_session))),
            base_url="http://testserver",
        ) as fresh_client:
            for job, expected in ((original.json(), retained), (refreshed.json(), corrected)):
                stored = await AnalyticsExportRepository(fresh_session).get_job(job["job_id"])
                assert stored is not None and stored.result_payload["data"] == expected["data"]
                for compression in ("none", "gzip"):
                    response = await fresh_client.get(
                        job["result_endpoint"],
                        params={"result_format": "ndjson", "compression": compression},
                    )
                    assert response.status_code == 200
                    # HTTPX decodes Content-Encoding, independently of NDJSON framing.
                    payload = response.content
                    if payload.startswith(b"\x1f\x8b"):
                        payload = gzip.decompress(payload)
                    lines = [json.loads(line) for line in payload.splitlines()]
                    assert lines[0]["source_evidence"] == expected["source_evidence"]
                    assert [line["record"] for line in lines[1:]] == expected["data"]
                reread = await fresh_client.get(job["result_endpoint"])
                assert reread.json() == expected


def economic_rows(payload, dataset):
    return payload["observations" if dataset == "portfolio" else "rows"]


def ending_value(row, dataset):
    return Decimal(
        row[
            "ending_market_value"
            if dataset == "portfolio"
            else "ending_market_value_reporting_currency"
        ]
    )


@pytest.mark.parametrize("dataset", ["portfolio", "position"])
@pytest.mark.parametrize("correction", ["valuation", "fx", "flow"])
async def test_db_corrections_change_http_content_but_not_request_identity(
    content_identity_client, dataset, correction
):
    client, session = content_identity_client
    original = await read_page(client, dataset)
    repeated = await read_page(client, dataset)
    assert original.status_code == repeated.status_code == 200
    before, repeat = original.json(), repeated.json()
    assert before["content_hash"] == repeat["content_hash"] == before["source_digest"]
    assert before["lineage"]["generated_at"] != repeat["lineage"]["generated_at"]
    assert ending_value(economic_rows(before, dataset)[0], dataset) == Decimal("220")
    if correction == "valuation":
        statement = (
            update(PositionTimeseries)
            .where(
                PositionTimeseries.portfolio_id == PORTFOLIO_ID,
                PositionTimeseries.date == FIRST_DAY,
            )
            .values(eod_market_value=Decimal("115"))
        )
    elif correction == "fx":
        statement = update(FxRate).where(FxRate.rate_date == FIRST_DAY).values(rate=Decimal("3"))
    else:
        statement = (
            update(Cashflow)
            .where(Cashflow.transaction_id == TRANSACTION_ID)
            .values(amount=Decimal("7"))
        )
    await session.execute(statement)
    await session.commit()
    corrected_response = await read_page(client, dataset)
    assert corrected_response.status_code == 200
    after = corrected_response.json()
    assert before["content_hash"] != after["content_hash"] == after["source_digest"]
    assert before["lineage"]["request_fingerprint"] == after["lineage"]["request_fingerprint"]
    assert before["page"]["snapshot_epoch"] == after["page"]["snapshot_epoch"] == 1
    corrected_row = economic_rows(after, dataset)[0]
    expected_ending = {"valuation": "230", "fx": "330", "flow": "220"}[correction]
    assert ending_value(corrected_row, dataset) == Decimal(expected_ending)
    if correction == "flow":
        assert Decimal(corrected_row["cash_flows"][0]["amount"]) == Decimal(
            "14" if dataset == "portfolio" else "7"
        )
    assert after["source_cut_id"] is None
    assert after["source_lineage"]["content_identity_scope"] == "response_page"
    assert after["source_lineage"]["source_cut_status"] == "UNAVAILABLE"


@pytest.mark.parametrize("dataset", ["portfolio", "position"])
async def test_http_paging_is_page_identity_not_complete_cut(content_identity_client, dataset):
    client, _ = content_identity_client
    first_response = await read_page(client, dataset, page_size=1)
    assert first_response.status_code == 200
    first = first_response.json()
    token = first["page"]["next_page_token"]
    assert token is not None
    second_response = await read_page(client, dataset, page_size=1, page_token=token)
    repeated = await read_page(client, dataset, page_size=1)
    assert second_response.status_code == repeated.status_code == 200
    second = second_response.json()
    assert first["content_hash"] == repeated.json()["content_hash"] != second["content_hash"]
    assert ending_value(economic_rows(first, dataset)[0], dataset) == Decimal("220")
    assert ending_value(economic_rows(second, dataset)[0], dataset) == Decimal("240")
    for payload in (first, second):
        assert payload["data_quality_status"] == "PARTIAL"
        assert payload["source_cut_id"] is None
        assert payload["source_lineage"]["content_identity_scope"] == "response_page"


@pytest.mark.parametrize("dataset", ["portfolio", "position"])
async def test_missing_fx_refuses_http_economics_not_a_usable_empty_digest(
    content_identity_client, dataset
):
    client, session = content_identity_client
    await session.execute(delete(FxRate).where(FxRate.rate_date == FIRST_DAY))
    await session.commit()
    response = await read_page(client, dataset)
    assert response.status_code == 422
    assert response.json()["error_code"] == "QCP_ANALYTICS_INSUFFICIENT_DATA"
    assert "content_hash" not in response.json()
