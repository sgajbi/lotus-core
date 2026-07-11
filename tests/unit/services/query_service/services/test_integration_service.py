"""Tests for the remaining Query Service reference taxonomy facade."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from portfolio_common.reconciliation_quality import BLOCKED, PARTIAL
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.services.integration_service import (
    IntegrationService,
    IntegrationServiceDependencies,
)
from src.services.query_service.app.services.reference_data_helpers import (
    latest_reference_evidence_timestamp,
    market_reference_data_quality_status,
)


def make_service() -> IntegrationService:
    return IntegrationService(AsyncMock(spec=AsyncSession))


def test_integration_service_accepts_explicit_repository_dependency() -> None:
    reference_repository = AsyncMock()

    service = IntegrationService(
        dependencies=IntegrationServiceDependencies(
            reference_repository=reference_repository,
        )
    )

    assert service.db is None
    assert service._reference_repository is reference_repository  # noqa: SLF001


def test_market_reference_quality_classifies_partial_blocked_and_unknown() -> None:
    rows = [
        SimpleNamespace(quality_status="accepted"),
        SimpleNamespace(quality_status="estimated"),
        SimpleNamespace(quality_status="accepted"),
    ]

    assert market_reference_data_quality_status(rows, required_count=3) == PARTIAL
    assert (
        market_reference_data_quality_status(
            [SimpleNamespace(quality_status="blocked")], required_count=1
        )
        == BLOCKED
    )
    assert market_reference_data_quality_status([SimpleNamespace()], required_count=1) == "UNKNOWN"


def test_latest_reference_evidence_uses_durable_timestamps() -> None:
    older_source_timestamp = datetime(2026, 1, 2, 9, 0, tzinfo=UTC)
    latest_updated_at = datetime(2026, 1, 3, 11, 0, tzinfo=UTC)

    assert (
        latest_reference_evidence_timestamp(
            [
                SimpleNamespace(source_timestamp=older_source_timestamp),
                SimpleNamespace(updated_at=latest_updated_at),
            ]
        )
        == latest_updated_at
    )


@pytest.mark.asyncio
async def test_classification_taxonomy_delegates_to_repository() -> None:
    service = make_service()
    repository = SimpleNamespace(
        list_taxonomy=AsyncMock(
            return_value=[
                SimpleNamespace(
                    classification_set_id="set1",
                    taxonomy_scope="index",
                    dimension_name="sector",
                    dimension_value="technology",
                    dimension_description="Technology",
                    effective_from=date(2026, 1, 1),
                    effective_to=None,
                    quality_status="accepted",
                )
            ]
        ),
    )
    service._reference_repository = repository  # type: ignore[assignment]  # noqa: SLF001

    taxonomy = await service.get_classification_taxonomy(as_of_date=date(2026, 1, 1))

    assert taxonomy.records[0].dimension_name == "sector"
    assert taxonomy.request_fingerprint
