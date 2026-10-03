"""Registered model-definition admission over migrated PostgreSQL persistence.

Job bookkeeping and replay lookup are explicit doubles; request validation, command
orchestration, the registry and model persistence run their production paths.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
from portfolio_common.database_models import ModelPortfolioDefinition
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
from tests.test_support.tenant import TEST_TENANT_HEADERS

pytestmark = [pytest.mark.asyncio, pytest.mark.integration_db, pytest.mark.db_direct]
TEST_MODEL_IDS = ("MODEL_IDENTITY_PG", "MODEL_UNPERSISTED_PG")


@pytest_asyncio.fixture
async def isolated_model_definitions(clean_db, async_db_session: AsyncSession):
    """Own only synthetic model rows; shared cleanup intentionally leaves this table intact."""

    async def remove_owned_rows() -> None:
        await async_db_session.rollback()
        await async_db_session.execute(
            delete(ModelPortfolioDefinition).where(
                ModelPortfolioDefinition.model_portfolio_id.in_(TEST_MODEL_IDS)
            )
        )
        await async_db_session.commit()

    await remove_owned_rows()
    try:
        yield
    finally:
        await remove_owned_rows()


def _definition(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "model_portfolio_id": "MODEL_IDENTITY_PG",
        "model_portfolio_version": "v1",
        "display_name": "Synthetic imported model",
        "base_currency": "USD",
        "risk_profile": "balanced",
        "mandate_type": "discretionary",
        "approval_status": "approved",
        "effective_from": "2026-03-01",
        "source_system": "synthetic_model_feed",
        "source_record_id": "MODEL-IDENTITY-1",
        "observed_at": "2026-03-01T00:00:00Z",
    }
    record.update(overrides)
    return record


async def _stored_rows(session: AsyncSession) -> list[dict[str, object]]:
    result = await session.execute(
        select(ModelPortfolioDefinition.__table__).order_by(ModelPortfolioDefinition.id)
    )
    return [dict(row) for row in result.mappings()]


@pytest.mark.parametrize("repetition", (1, 2))
async def test_model_definition_identity_refusal_has_no_job_or_database_side_effects(
    isolated_model_definitions, async_db_session: AsyncSession, repetition: int
) -> None:
    jobs = MagicMock(spec=IngestionJobService)
    jobs.assert_ingestion_writable = AsyncMock()
    jobs.create_or_get_job = AsyncMock(
        return_value=SimpleNamespace(created=True, job=SimpleNamespace(job_id="MODEL-IDENTITY-JOB"))
    )
    jobs.mark_queued = AsyncMock(return_value=True)
    jobs.mark_failed = AsyncMock()
    replay = SimpleNamespace(find_matching_job=AsyncMock(return_value=None))
    persistence = MagicMock(spec=ReferenceDataIngestionService)
    persistence.upsert_model_portfolio_definitions = AsyncMock(
        wraps=ReferenceDataIngestionService(async_db_session).upsert_model_portfolio_definitions
    )
    handler = ReferenceDataIngestionCommandHandler(persistence, jobs, replay)
    assert get_reference_data_ingestion_command_handler not in app.dependency_overrides
    app.dependency_overrides[get_reference_data_ingestion_command_handler] = lambda: handler
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
            headers={**TEST_TENANT_HEADERS, "X-Lotus-Ops-Token": "lotus-core-ops-local"},
        ) as client:
            existing = await client.post(
                "/ingest/model-portfolios", json={"model_portfolios": [_definition()]}
            )
            assert existing.status_code == 202, existing.text
            assert existing.json()["accepted_count"] == 1
            baseline = await _stored_rows(async_db_session)
            assert sum(row["model_portfolio_id"] in TEST_MODEL_IDS for row in baseline) == 1

            for conflicting in (False, True):
                for reverse in (False, True):
                    for mixed in (False, True):
                        records = [
                            _definition(),
                            _definition(approval_status="suspended" if conflicting else "approved"),
                        ]
                        if reverse:
                            records.reverse()
                        if mixed:
                            records.insert(
                                1, _definition(model_portfolio_id="MODEL_UNPERSISTED_PG")
                            )
                        calls_before = list(jobs.mock_calls)
                        persistence_calls = (
                            persistence.upsert_model_portfolio_definitions.call_count
                        )
                        replay_calls = replay.find_matching_job.call_count
                        refused = await client.post(
                            "/ingest/model-portfolios", json={"model_portfolios": records}
                        )
                        assert refused.status_code == 422, refused.text
                        error = refused.json()["detail"][0]
                        assert error["type"] == "DUPLICATE_SOURCE_KEY"
                        assert error["ctx"]["field_path"] == "model_portfolios"
                        assert jobs.mock_calls == calls_before
                        assert persistence.upsert_model_portfolio_definitions.call_count == (
                            persistence_calls
                        )
                        assert replay.find_matching_job.call_count == replay_calls
                        assert await _stored_rows(async_db_session) == baseline

            controls = [
                _definition(model_portfolio_version="v2", source_record_id="MODEL-IDENTITY-2"),
                _definition(effective_from="2026-04-01", source_record_id="MODEL-IDENTITY-3"),
            ]
            accepted = await client.post(
                "/ingest/model-portfolios", json={"model_portfolios": controls}
            )
            assert accepted.status_code == 202, accepted.text
            assert accepted.json()["accepted_count"] == 2
            rows = [
                row
                for row in await _stored_rows(async_db_session)
                if row["model_portfolio_id"] in TEST_MODEL_IDS
            ]
            assert len(rows) == 3
            assert {
                (row["model_portfolio_version"], str(row["effective_from"])) for row in rows
            } == {("v1", "2026-03-01"), ("v2", "2026-03-01"), ("v1", "2026-04-01")}
            assert {row["source_record_id"] for row in rows} == {
                "MODEL-IDENTITY-1",
                "MODEL-IDENTITY-2",
                "MODEL-IDENTITY-3",
            }
            assert all(row["base_currency"] == "USD" for row in rows)
            assert all(row["source_system"] == "synthetic_model_feed" for row in rows)
            assert all(row["approval_status"] == "approved" for row in rows)
            assert jobs.create_or_get_job.call_count == 2
            assert jobs.mark_queued.call_count == 2
            jobs.mark_failed.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_reference_data_ingestion_command_handler)
