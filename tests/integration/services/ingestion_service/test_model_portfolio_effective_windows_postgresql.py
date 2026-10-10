"""Registered HTTP, real command/persistence and fresh-session effective reads.

Job bookkeeping and replay lookup are explicit doubles, as in the owning model
identity cohort. This proves source upsert replay, not durable job replay or Kafka.
"""

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
from portfolio_common.database_models import ModelPortfolioDefinition, ModelPortfolioTarget
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.ingestion_service.app.dependencies import (
    get_reference_data_ingestion_command_handler,
)
from src.services.ingestion_service.app.main import app
from src.services.ingestion_service.app.services.ingestion_job_service import IngestionJobService
from src.services.ingestion_service.app.services.reference_data_ingestion_commands import (
    ReferenceDataIngestionCommandHandler,
)
from src.services.ingestion_service.app.services.reference_data_ingestion_service import (
    ReferenceDataIngestionService,
)
from src.services.query_control_plane_service.app.infrastructure.dpm_reference_data_sources import (
    SqlAlchemyDpmReferenceDataReader,
)
from tests.test_support.tenant import TEST_TENANT_HEADERS

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]
MODEL_ID = "MODEL_EFFECTIVE_WINDOW_PG"
FAMILIES = (
    ("/ingest/model-portfolios", "model_portfolios", ModelPortfolioDefinition),
    ("/ingest/model-portfolio-targets", "model_portfolio_targets", ModelPortfolioTarget),
)


def _record(model, start="2026-09-01", end=None):
    values = dict(
        model_portfolio_id=MODEL_ID,
        model_portfolio_version="v1",
        effective_from=start,
        effective_to=end,
        source_system="synthetic_model_feed",
        source_record_id="WINDOW-ORIGINAL",
        observed_at="2026-09-01T00:00:00Z",
    )
    if model is ModelPortfolioTarget:
        values.update(instrument_id="WINDOW_EQ", target_weight="0.6000000000")
    else:
        values.update(
            display_name="Synthetic imported model",
            base_currency="USD",
            risk_profile="balanced",
            mandate_type="discretionary",
            approval_status="approved",
        )
    return values


async def _stored(session, model):
    async with AsyncSession(bind=session.bind) as fresh:
        rows = await fresh.execute(
            select(model.__table__).where(model.model_portfolio_id == MODEL_ID)
        )
        return [dict(row) for row in rows.mappings()]


async def _selected(session, model, as_of):
    async with AsyncSession(bind=session.bind) as fresh:
        reader = SqlAlchemyDpmReferenceDataReader(fresh)
        if model is ModelPortfolioDefinition:
            return await reader.resolve_model_portfolio_definition(
                model_portfolio_id=MODEL_ID, as_of_date=as_of
            )
        result = await reader.list_model_portfolio_targets(
            model_portfolio_id=MODEL_ID,
            model_portfolio_version="v1",
            as_of_date=as_of,
            include_inactive_targets=True,
        )
        assert not result.limit_exceeded
        assert len(result.records) <= 1
        return result.records[0] if result.records else None


@pytest_asyncio.fixture
async def model_ingress(clean_db, async_db_session):
    async def remove_owned_rows():
        await async_db_session.rollback()
        for _, _, model in FAMILIES:
            await async_db_session.execute(
                delete(model).where(model.model_portfolio_id == MODEL_ID)
            )
        await async_db_session.commit()

    await remove_owned_rows()
    jobs = MagicMock(spec=IngestionJobService)
    jobs.assert_ingestion_writable = AsyncMock()
    jobs.create_or_get_job = AsyncMock(
        return_value=SimpleNamespace(created=True, job=SimpleNamespace(job_id="WINDOW-JOB"))
    )
    jobs.mark_queued = AsyncMock(return_value=True)
    jobs.mark_failed = AsyncMock()
    replay = SimpleNamespace(find_matching_job=AsyncMock(return_value=None))
    persistence = MagicMock(spec=ReferenceDataIngestionService)
    service = ReferenceDataIngestionService(async_db_session)
    for method in ("upsert_model_portfolio_definitions", "upsert_model_portfolio_targets"):
        setattr(persistence, method, AsyncMock(wraps=getattr(service, method)))
    handler = ReferenceDataIngestionCommandHandler(persistence, jobs, replay)
    dispatch = AsyncMock(wraps=handler.ingest_reference_data)
    assert get_reference_data_ingestion_command_handler not in app.dependency_overrides
    app.dependency_overrides[get_reference_data_ingestion_command_handler] = lambda: (
        SimpleNamespace(ingest_reference_data=dispatch)
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
            headers={**TEST_TENANT_HEADERS, "X-Lotus-Ops-Token": "lotus-core-ops-local"},
        ) as client:
            yield client, jobs, persistence, replay, dispatch
    finally:
        app.dependency_overrides.pop(get_reference_data_ingestion_command_handler)
        await remove_owned_rows()


@pytest.mark.parametrize(("endpoint", "field", "model"), FAMILIES)
@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-09-01", None),
        ("2026-09-01", "2026-09-01"),
        ("2026-09-01", "2026-09-30"),
        ("2000-01-01", "2000-01-31"),
        ("2099-01-01", "2099-01-31"),
    ],
)
async def test_registered_model_windows_preserve_inclusive_boundaries(
    model_ingress, async_db_session, endpoint, field, model, start, end
):
    client, jobs, _, _, _ = model_ingress
    payload = {field: [_record(model, start, end)]}
    accepted = await client.post(endpoint, json=payload)
    assert accepted.status_code == 202, accepted.text
    original = await _stored(async_db_session, model)
    assert len(original) == 1
    assert original[0]["source_record_id"] == "WINDOW-ORIGINAL"
    if model is ModelPortfolioTarget:
        assert original[0]["target_weight"] == Decimal("0.6000000000")
    repeated = await client.post(endpoint, json=payload)
    assert repeated.status_code == 202, repeated.text
    reloaded = await _stored(async_db_session, model)
    # The existing source upsert refreshes its server-owned updated_at timestamp.
    # Every other field, including identity, creation time and exact weight, is stable.
    assert [{k: v for k, v in row.items() if k != "updated_at"} for row in reloaded] == [
        {k: v for k, v in row.items() if k != "updated_at"} for row in original
    ]
    assert reloaded[0]["updated_at"] >= original[0]["updated_at"]
    first = date.fromisoformat(start)
    last = date.fromisoformat(end) if end else first + timedelta(days=365)
    assert await _selected(async_db_session, model, first - timedelta(days=1)) is None
    for boundary in {first, last}:
        row = await _selected(async_db_session, model, boundary)
        assert row is not None
        assert row.effective_from == first
        assert row.effective_to == (date.fromisoformat(end) if end else None)
        if model is ModelPortfolioTarget:
            assert row.target_weight == Decimal("0.6000000000")
    if end:
        assert await _selected(async_db_session, model, last + timedelta(days=1)) is None
    jobs.mark_failed.assert_not_called()


@pytest.mark.parametrize(("endpoint", "field", "model"), FAMILIES)
async def test_registered_invalid_model_correction_refuses_before_dispatch_and_preserves_source(
    model_ingress, async_db_session, endpoint, field, model
):
    client, jobs, persistence, replay, dispatch = model_ingress
    record = _record(model, end="2026-09-30")
    empty = await _stored(async_db_session, model)
    assert empty == []
    refused = await client.post(endpoint, json={field: [{**record, "effective_to": "2026-08-31"}]})
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"][0]["ctx"]["field_path"] == "effective_to"
    dispatch.assert_not_called()
    assert jobs.mock_calls == persistence.mock_calls == []
    replay.find_matching_job.assert_not_called()
    assert await _stored(async_db_session, model) == empty
    accepted = await client.post(endpoint, json={field: [record]})
    assert accepted.status_code == 202, accepted.text
    original = await _stored(async_db_session, model)
    for mixed in (False, True):
        records = [{**record, "effective_to": "2026-08-31", "source_record_id": "BAD"}]
        if mixed:
            records.insert(0, {**record, "model_portfolio_id": MODEL_ID + "_UNWRITTEN"})
        counters = (
            dispatch.call_count,
            list(jobs.mock_calls),
            list(persistence.mock_calls),
            replay.find_matching_job.call_count,
        )
        refused = await client.post(endpoint, json={field: records})
        assert refused.status_code == 422, refused.text
        error = refused.json()["detail"][0]
        assert error["type"] == "INVALID_EFFECTIVE_WINDOW"
        assert error["ctx"]["field_path"] == "effective_to"
        assert (
            dispatch.call_count,
            jobs.mock_calls,
            persistence.mock_calls,
            replay.find_matching_job.call_count,
        ) == counters
        assert await _stored(async_db_session, model) == original
        async with AsyncSession(bind=async_db_session.bind) as fresh:
            assert (
                await fresh.execute(
                    select(model.id).where(model.model_portfolio_id == MODEL_ID + "_UNWRITTEN")
                )
            ).first() is None
    corrected = {**record, "effective_to": "2026-10-31", "source_record_id": "WINDOW-CORRECTED"}
    accepted = await client.post(endpoint, json={field: [corrected]})
    assert accepted.status_code == 202, accepted.text
    rows = await _stored(async_db_session, model)
    assert len(rows) == 1
    assert rows[0]["id"] == original[0]["id"]
    assert rows[0]["source_record_id"] == "WINDOW-CORRECTED"
    row = await _selected(async_db_session, model, date(2026, 10, 31))
    assert row is not None and row.effective_to == date(2026, 10, 31)
    if model is ModelPortfolioTarget:
        assert row.target_weight == Decimal("0.6000000000")
    assert await _selected(async_db_session, model, date(2026, 11, 1)) is None
