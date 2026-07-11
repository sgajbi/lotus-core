"""Tests for QCP classification taxonomy orchestration and source proof."""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest

from src.services.query_control_plane_service.app.application.classification_taxonomy import (
    ClassificationTaxonomyService,
)
from src.services.query_control_plane_service.app.contracts.classification_taxonomy import (
    ClassificationTaxonomyRequest,
)
from src.services.query_control_plane_service.app.domain.classification_taxonomy import (
    ClassificationTaxonomyEvidence,
)

AS_OF_DATE = date(2026, 4, 10)
EVIDENCE_TIME = datetime(2026, 4, 10, 9, tzinfo=UTC)


def _record(
    *, dimension_value: str, quality_status: str = "accepted"
) -> ClassificationTaxonomyEvidence:
    return ClassificationTaxonomyEvidence(
        classification_set_id="wm_global_taxonomy_v1",
        taxonomy_scope="instrument",
        dimension_name="asset_class",
        dimension_value=dimension_value,
        dimension_description=dimension_value.title(),
        effective_from=date(2026, 1, 1),
        effective_to=None,
        quality_status=quality_status,
        observed_at=EVIDENCE_TIME,
        source_vendor="lotus-reference",
        source_record_id=f"taxonomy-{dimension_value}",
        created_at=EVIDENCE_TIME,
        updated_at=EVIDENCE_TIME,
    )


@pytest.mark.asyncio
async def test_service_reads_scope_and_returns_current_source_proof() -> None:
    reader = AsyncMock()
    reader.list_effective.return_value = [_record(dimension_value="equity")]
    service = ClassificationTaxonomyService(
        reader=reader,
        clock=lambda: datetime(2026, 4, 10, 10, tzinfo=UTC),
    )
    request = ClassificationTaxonomyRequest(
        as_of_date=AS_OF_DATE,
        taxonomy_scope="instrument",
    )

    response = await service.get(request=request)

    reader.list_effective.assert_awaited_once_with(
        as_of_date=AS_OF_DATE,
        taxonomy_scope="instrument",
    )
    assert response.records[0].dimension_value == "equity"
    assert response.generated_at == datetime(2026, 4, 10, 10, tzinfo=UTC)
    assert response.latest_evidence_timestamp == EVIDENCE_TIME
    assert response.data_quality_status == "COMPLETE"
    assert response.freshness_status == "CURRENT"
    assert response.source_evidence_current is True
    assert response.content_hash
    assert response.source_batch_fingerprint == response.content_hash
    assert response.source_refs
    assert response.source_lineage["source_owner"] == "lotus-core"


@pytest.mark.asyncio
async def test_content_hash_is_independent_of_source_order_and_generation_time() -> None:
    first_reader = AsyncMock()
    second_reader = AsyncMock()
    equity = _record(dimension_value="equity")
    bond = _record(dimension_value="bond")
    first_reader.list_effective.return_value = [equity, bond]
    second_reader.list_effective.return_value = [bond, equity]
    request = ClassificationTaxonomyRequest(as_of_date=AS_OF_DATE)

    first = await ClassificationTaxonomyService(
        reader=first_reader,
        clock=lambda: datetime(2026, 4, 10, 10, tzinfo=UTC),
    ).get(request=request)
    second = await ClassificationTaxonomyService(
        reader=second_reader,
        clock=lambda: datetime(2026, 4, 10, 11, tzinfo=UTC),
    ).get(request=request)

    assert first.content_hash == second.content_hash
    assert [record.dimension_value for record in first.records] == ["bond", "equity"]


@pytest.mark.asyncio
async def test_stale_taxonomy_is_not_reported_as_current() -> None:
    reader = AsyncMock()
    reader.list_effective.return_value = [_record(dimension_value="equity", quality_status="stale")]
    response = await ClassificationTaxonomyService(
        reader=reader,
        clock=lambda: datetime(2026, 4, 10, 10, tzinfo=UTC),
    ).get(request=ClassificationTaxonomyRequest(as_of_date=AS_OF_DATE))

    assert response.data_quality_status == "STALE"
    assert response.freshness_status == "STALE"
    assert response.source_evidence_current is False
