"""Registered QCP HTTP ownership must precede analytics observations and identities."""

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from portfolio_common import db as database_provider
from portfolio_common.database_models import (
    AnalyticsExportJob,
    BusinessDate,
    Instrument,
    Portfolio,
    PortfolioTimeseries,
    PositionHistory,
    PositionState,
    PositionTimeseries,
    Transaction,
)
from portfolio_common.domain.tenant import TenantId
from portfolio_common.request_fingerprints import request_fingerprint
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.services.query_control_plane_service.app.application.analytics.analytics_export_corrections import (  # noqa: E501
    export_request_payload,
)
from src.services.query_control_plane_service.app.contracts.analytics_inputs import (
    AnalyticsExportCreateRequest,
)
from src.services.query_control_plane_service.app.infrastructure.analytics_export_repository import (  # noqa: E501
    AnalyticsExportRepository,
    _export_job_record,
)
from src.services.query_control_plane_service.app.main import app

pytestmark = [pytest.mark.asyncio, pytest.mark.db_direct]
DAYS = (date(2026, 4, 10), date(2026, 4, 13))
OWNERS = (
    ("tenant-analytics-a", "ANALYTICS_OWNER_A", "100"),
    ("tenant-analytics-b", "ANALYTICS_OWNER_B", "300"),
)
SECURITY = "ANALYTICS_OWNER_SECURITY"


@pytest_asyncio.fixture
async def export_case(clean_db, async_db_session, request):
    """Own durable export rows for one stable, independently repeatable test case."""
    namespace = sha256(request.node.nodeid.encode()).hexdigest()[:32]
    prefix = f"aexp_tenant_custody_{namespace}_"
    owners = (
        (f"tenant-export-{namespace}-a", f"EXPORT_{namespace}_A"),
        (f"tenant-export-{namespace}-b", f"EXPORT_{namespace}_B"),
    )
    portfolios = (owners[0][1], owners[1][1], f"EXPORT_{namespace}_ORPHAN")
    scope = or_(
        AnalyticsExportJob.job_id.startswith(prefix, autoescape=True),
        AnalyticsExportJob.portfolio_id.in_(portfolios),
    )

    async def release_owned_rows():
        await async_db_session.rollback()
        await async_db_session.execute(delete(AnalyticsExportJob).where(scope))
        await async_db_session.commit()
        remaining = await async_db_session.execute(select(AnalyticsExportJob.job_id).where(scope))
        assert remaining.scalars().all() == []
        await async_db_session.rollback()

    # The shared financial-table fixture omits this no-FK durable table. Clean
    # only our case's namespace, including orphan rows and unexpected new jobs
    # for its named portfolios; all other retained exports remain untouched.
    await release_owned_rows()
    try:
        yield SimpleNamespace(
            owners=owners,
            portfolios=portfolios,
            scope=scope,
            job_ids={
                suffix: f"{prefix}{suffix}"
                for suffix in ("owner", "foreign", "orphan", "missing", "denied")
            },
        )
    finally:
        await release_owned_rows()


async def _seed_export_owners(session, monkeypatch, dataset, case):
    for tenant, portfolio in case.owners:
        session.add(
            Portfolio(
                tenant_id=tenant,
                portfolio_id=portfolio,
                base_currency="USD",
                open_date=DAYS[0],
                risk_exposure="BALANCED",
                investment_time_horizon="LONG_TERM",
                portfolio_type="discretionary",
                booking_center_code="Singapore",
                client_id=f"CLIENT_{portfolio}",
                status="active",
            )
        )
    request = AnalyticsExportCreateRequest.model_validate(
        {
            "dataset_type": dataset,
            "portfolio_id": case.owners[0][1],
            f"{dataset}_request": {"as_of_date": DAYS[-1].isoformat(), "period": "one_month"},
        }
    )
    payload = export_request_payload(request)
    fingerprint = request_fingerprint(payload)
    jobs = []
    for suffix, portfolio in (
        ("owner", case.owners[0][1]),
        ("foreign", case.owners[1][1]),
        ("orphan", case.portfolios[2]),
    ):
        job_id = case.job_ids[suffix]
        result = {
            "job_id": job_id,
            "dataset_type": dataset,
            "request_fingerprint": fingerprint,
            "generated_at": datetime.now(UTC).isoformat(),
            "contract_version": "rfc_063_v1",
            "result_row_count": 1,
            "data": [{"retained": suffix}],
        }
        # Deliberately colliding fingerprints exercise the tenant SQL predicate,
        # independent of normal request fingerprint uniqueness.
        job = AnalyticsExportJob(
            job_id=job_id,
            portfolio_id=portfolio,
            dataset_type=dataset,
            request_fingerprint=fingerprint,
            request_payload=payload,
            status="completed",
            result_payload=result,
            result_row_count=1,
            result_format="json",
            compression="none",
        )
        session.add(job)
        jobs.append(job)
        await session.flush()
    await session.commit()
    monkeypatch.setattr(
        database_provider,
        "AsyncSessionLocal",
        async_sessionmaker(bind=session.bind, expire_on_commit=False),
    )
    return request, fingerprint, jobs


@pytest.mark.parametrize("dataset", ["portfolio_timeseries", "position_timeseries"])
@pytest.mark.parametrize(
    "format_,compression", [("json", "none"), ("ndjson", "none"), ("ndjson", "gzip")]
)
async def test_registered_export_owner_reads_and_reuse_fail_closed(
    export_case, async_db_session, monkeypatch, dataset, format_, compression
):
    case = export_case
    request, fingerprint, jobs = await _seed_export_owners(
        async_db_session, monkeypatch, dataset, case
    )
    base = "/integration/exports/analytics-timeseries/jobs"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        owner_headers = {"X-Tenant-Id": case.owners[0][0]}
        reused = await client.post(
            base, headers=owner_headers, json=request.model_dump(mode="json")
        )
        assert reused.status_code == 200, reused.text
        assert reused.json()["job_id"] == case.job_ids["owner"]
        status = await client.get(f"{base}/{case.job_ids['owner']}", headers=owner_headers)
        assert status.status_code == 200 and status.json()["status"] == "completed"
        owner = await client.get(
            f"{base}/{case.job_ids['owner']}/result",
            headers=owner_headers,
            params={"result_format": format_, "compression": compression},
        )
        assert owner.status_code == 200, owner.text
        assert "owner" in owner.text
        problems = {"": [], "/result": []}
        for suffix in ("foreign", "orphan", "missing"):
            for tail in ("", "/result"):
                response = await client.get(
                    f"{base}/{case.job_ids[suffix]}{tail}",
                    headers=owner_headers,
                    params={"result_format": format_, "compression": compression},
                )
                assert response.status_code == 404, response.text
                problem = response.json()
                assert problem["error_code"] == "QCP_ANALYTICS_NOT_FOUND"
                assert problem["detail"] == "Requested analytics source was not found."
                assert "retained" not in response.text
                assert fingerprint not in response.text
                problem.pop("instance")
                problem.pop("correlation_id")
                problems[tail].append(problem)
        assert all(group[0] == group[1] == group[2] for group in problems.values())
        for anchor in (case.job_ids[suffix] for suffix in ("foreign", "orphan", "missing")):
            refused = await client.post(
                base,
                headers=owner_headers,
                json={**request.model_dump(mode="json"), "refresh_of_job_id": anchor},
            )
            assert refused.status_code == 404, refused.text
        refused = await client.post(
            base, headers={"X-Tenant-Id": case.owners[1][0]}, json=request.model_dump(mode="json")
        )
        assert refused.status_code == 404, refused.text
    retained = (
        (await async_db_session.execute(select(AnalyticsExportJob).where(case.scope)))
        .scalars()
        .all()
    )
    assert len(retained) == len(jobs) == 3
    assert {job.job_id for job in retained} == {
        case.job_ids[suffix] for suffix in ("owner", "foreign", "orphan")
    }
    assert all(job.status == "completed" for job in retained)
    assert {job.job_id: job.result_payload["data"] for job in retained} == {
        case.job_ids[suffix]: [{"retained": suffix}] for suffix in ("owner", "foreign", "orphan")
    }


@pytest.mark.parametrize("dataset", ["portfolio_timeseries", "position_timeseries"])
async def test_export_primary_owner_fences_creation_stale_and_lifecycle(
    export_case, async_db_session, monkeypatch, dataset
):
    case = export_case
    request, fingerprint, jobs = await _seed_export_owners(
        async_db_session, monkeypatch, dataset, case
    )
    session = async_db_session
    owner = AnalyticsExportRepository(session, tenant_id=TenantId(case.owners[0][0]))
    foreign = AnalyticsExportRepository(session, tenant_id=TenantId(case.owners[1][0]))
    assert (
        await owner.get_latest_by_fingerprint(request_fingerprint=fingerprint, dataset_type=dataset)
    ).job_id == case.job_ids["owner"]
    owner_record, orphan_record = _export_job_record(jobs[0]), _export_job_record(jobs[2])
    foreign_record = _export_job_record(jobs[1])
    for store, record in ((foreign, owner_record), (owner, orphan_record)):
        for transition in ("running", "completed", "failed"):
            with pytest.raises(LookupError):
                if transition == "running":
                    await store.mark_running(record)
                elif transition == "completed":
                    await store.mark_completed(record, result_payload={}, result_row_count=0)
                else:
                    await store.mark_failed(record, error_message="stale")
    for portfolio in (case.owners[1][1], case.portfolios[2]):
        with pytest.raises(LookupError, match="Portfolio not found"):
            await owner.create_job(
                job_id=case.job_ids["denied"],
                dataset_type=dataset,
                portfolio_id=portfolio,
                request_fingerprint="denied",
                request_payload={},
                result_format="json",
                compression="none",
            )
    jobs[0].status = "running"
    jobs[0].started_at = datetime.now(UTC) - timedelta(days=1)
    jobs[0].updated_at = jobs[0].started_at
    await session.commit()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        refused = await client.post(
            "/integration/exports/analytics-timeseries/jobs",
            headers={"X-Tenant-Id": case.owners[1][0]},
            json=request.model_dump(mode="json"),
        )
        assert refused.status_code == 404, refused.text
    await session.refresh(jobs[0])
    assert jobs[0].status == "running"
    assert jobs[0].error_message is None
    # Valid ownership still permits all existing lifecycle transitions.
    running = await owner.mark_running(owner_record)
    completed = await owner.mark_completed(
        running, result_payload={"owned": True}, result_row_count=1
    )
    assert completed.status == "completed" and completed.result_payload == {"owned": True}
    assert (await owner.mark_failed(completed, error_message="owned failure")).status == "failed"
    for job, suffix, original in (
        (jobs[1], "foreign", foreign_record),
        (jobs[2], "orphan", orphan_record),
    ):
        await session.refresh(job)
        assert job.status == "completed"
        assert job.error_message is None
        assert job.result_payload["data"] == [{"retained": suffix}]
        assert _export_job_record(job) == original
    retained_ids = (
        await session.execute(select(AnalyticsExportJob.job_id).where(case.scope))
    ).scalars()
    assert set(retained_ids) == {case.job_ids[suffix] for suffix in ("owner", "foreign", "orphan")}


@pytest.mark.parametrize("dataset", ["portfolio", "position"])
async def test_registered_http_analytics_tenant_ownership(
    clean_db, async_db_session, monkeypatch, dataset
):
    """Use the real admission, composition, snapshot, service and PostgreSQL reader."""
    session = async_db_session
    session.add(
        Instrument(
            security_id=SECURITY,
            name="Analytics ownership equity",
            isin="ANALYTICS-OWNER",
            currency="USD",
            product_type="EQUITY",
            asset_class="Equity",
        )
    )
    session.add_all(BusinessDate(date=day) for day in DAYS)
    for tenant, portfolio, amount in OWNERS:
        session.add(
            Portfolio(
                tenant_id=tenant,
                portfolio_id=portfolio,
                base_currency="USD",
                open_date=DAYS[0],
                risk_exposure="BALANCED",
                investment_time_horizon="LONG_TERM",
                portfolio_type="discretionary",
                booking_center_code="Singapore",
                client_id=f"CLIENT_{portfolio}",
                status="active",
            )
        )
    await session.flush()
    for _, portfolio, amount in OWNERS:
        session.add(
            Transaction(
                transaction_id=f"{portfolio}_BUY",
                portfolio_id=portfolio,
                instrument_id=SECURITY,
                security_id=SECURITY,
                transaction_date=datetime(2026, 4, 10, 9, tzinfo=UTC),
                settlement_date=datetime(2026, 4, 10, 16, tzinfo=UTC),
                transaction_type="BUY",
                quantity=Decimal("10"),
                price=Decimal(amount) / 10,
                gross_transaction_amount=Decimal(amount),
                trade_currency="USD",
                currency="USD",
            )
        )
    await session.flush()
    for _, portfolio, amount in OWNERS:
        # Source admission requires a same-epoch historical quantity; a valuation
        # row alone cannot establish a supported current holding.
        session.add(
            PositionHistory(
                portfolio_id=portfolio,
                security_id=SECURITY,
                transaction_id=f"{portfolio}_BUY",
                position_date=DAYS[0],
                epoch=0,
                quantity=Decimal("10"),
                cost_basis=Decimal(amount),
                cost_basis_local=Decimal(amount),
            )
        )
        session.add(
            PositionState(
                portfolio_id=portfolio,
                security_id=SECURITY,
                epoch=0,
                watermark_date=DAYS[-1],
                status="CURRENT",
            )
        )
        for day in DAYS:
            value = Decimal(amount)
            session.add(
                PortfolioTimeseries(
                    portfolio_id=portfolio,
                    date=day,
                    epoch=0,
                    bod_market_value=value,
                    eod_market_value=value + 1,
                    bod_cashflow=0,
                    eod_cashflow=0,
                    fees=0,
                )
            )
            session.add(
                PositionTimeseries(
                    portfolio_id=portfolio,
                    security_id=SECURITY,
                    date=day,
                    epoch=0,
                    bod_market_value=value,
                    eod_market_value=value + 1,
                    bod_cashflow_position=0,
                    eod_cashflow_position=0,
                    bod_cashflow_portfolio=0,
                    eod_cashflow_portfolio=0,
                    fees=0,
                    quantity=10,
                    cost=value,
                )
            )
    await session.commit()
    monkeypatch.setattr(
        database_provider,
        "AsyncSessionLocal",
        async_sessionmaker(bind=session.bind, expire_on_commit=False),
    )
    body = {
        "as_of_date": DAYS[-1].isoformat(),
        "window": {"start_date": DAYS[0].isoformat(), "end_date": DAYS[-1].isoformat()},
        "page": {"page_size": 1},
    }
    if dataset == "position":
        body["include_cash_flows"] = False

    def endpoint(portfolio):
        return f"/integration/portfolios/{portfolio}/analytics/{dataset}-timeseries"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        for tenant, portfolio, amount in OWNERS:
            owned = await client.post(
                endpoint(portfolio), headers={"X-Tenant-Id": tenant}, json=body
            )
            assert owned.status_code == 200, owned.text
            data = owned.json()
            rows = data["observations" if dataset == "portfolio" else "rows"]
            assert len(rows) == 1
            value_key = (
                "ending_market_value"
                if dataset == "portfolio"
                else "ending_market_value_portfolio_currency"
            )
            assert Decimal(rows[0][value_key]) == Decimal(amount) + 1
            # Nullable response provenance is independent of admitted access authority.
            assert data["tenant_id"] is None
            repeated = await client.post(
                endpoint(portfolio), headers={"X-Tenant-Id": tenant}, json=body
            )
            assert repeated.status_code == 200, repeated.text
            assert repeated.json()["content_hash"] == data["content_hash"]
            assert (
                repeated.json()["lineage"]["request_fingerprint"]
                == data["lineage"]["request_fingerprint"]
            )
            token = data["page"]["next_page_token"]
            assert token
            continuation = {**body, "page": {"page_size": 1, "page_token": token}}
            next_page = await client.post(
                endpoint(portfolio), headers={"X-Tenant-Id": tenant}, json=continuation
            )
            assert next_page.status_code == 200, next_page.text
            assert (
                next_page.json()["page"]["request_scope_fingerprint"]
                == data["page"]["request_scope_fingerprint"]
            )
            foreign = next(owner[0] for owner in OWNERS if owner[0] != tenant)
            for selection in (
                body,
                continuation,
                {**body, "period": "inception", "window": None},
                {**body, "tenant_id": tenant},
                {**body, "page": {"page_size": 1, "page_token": "invalid-token"}},
            ):
                if dataset == "position":
                    selection = {
                        **selection,
                        "filters": {
                            "security_ids": [SECURITY],
                            "position_ids": [f"{portfolio}:{SECURITY}"],
                        },
                    }
                refused = await client.post(
                    endpoint(portfolio), headers={"X-Tenant-Id": foreign}, json=selection
                )
                missing = await client.post(
                    endpoint("ANALYTICS_MISSING"), headers={"X-Tenant-Id": foreign}, json=selection
                )
                assert refused.status_code == missing.status_code == 404
                problems = []
                for response in (refused, missing):
                    problem = response.json()
                    assert problem["error_code"] == "QCP_ANALYTICS_NOT_FOUND"
                    assert problem["detail"] == "Requested analytics source was not found."
                    # Existing problem instances echo the caller's own request path;
                    # correlation IDs identify each call. Neither identifies source state.
                    assert problem.pop("instance").startswith("/integration/portfolios/")
                    assert problem.pop("correlation_id")
                    safe_payload = json.dumps(problem)
                    assert portfolio not in safe_payload
                    assert tenant not in safe_payload
                    for source_field in (
                        "fingerprint",
                        "observations",
                        "lineage",
                        "content_hash",
                        "source_digest",
                        "rows",
                    ):
                        assert source_field not in safe_payload
                    problems.append(problem)
                assert problems[0] == problems[1]
            if dataset == "portfolio":
                reference = f"/integration/portfolios/{portfolio}/analytics/reference"
                reference_body = {"as_of_date": DAYS[-1].isoformat()}
                owned_reference = await client.post(
                    reference, headers={"X-Tenant-Id": tenant}, json=reference_body
                )
                assert owned_reference.status_code == 200, owned_reference.text
                foreign_reference = await client.post(
                    reference, headers={"X-Tenant-Id": foreign}, json=reference_body
                )
                assert foreign_reference.status_code == 404, foreign_reference.text
                reference_problem = foreign_reference.json()
                assert reference_problem.pop("instance") == reference
                assert portfolio not in json.dumps(reference_problem)
                assert "fingerprint" not in foreign_reference.text
        for headers in ({}, {"X-Tenant-Id": " "}):
            response = await client.post(endpoint(OWNERS[0][1]), headers=headers, json=body)
            assert response.status_code == 401, response.text
            assert "fingerprint" not in response.text
