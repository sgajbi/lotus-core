"""Application tests for the effective index definition catalog."""

from datetime import UTC, date, datetime

import pytest

from src.services.query_control_plane_service.app.application.index_catalog import (
    IndexCatalogService,
    build_index_catalog_response,
)
from src.services.query_control_plane_service.app.contracts.index_catalog import IndexCatalogRequest
from src.services.query_control_plane_service.app.domain.index_definition import (
    IndexDefinitionEvidence,
)

GENERATED_AT = datetime(2026, 4, 10, 12, tzinfo=UTC)
EVIDENCE_AT = datetime(2026, 4, 10, 10, tzinfo=UTC)
REQUEST = IndexCatalogRequest(as_of_date=date(2026, 4, 10))


def _definition(*, quality_status: str = "accepted") -> IndexDefinitionEvidence:
    return IndexDefinitionEvidence(
        index_id="IDX_MSCI_WORLD_TR",
        index_name="MSCI World Total Return",
        index_currency="USD",
        index_type="equity_index",
        index_status="active",
        index_provider="MSCI",
        index_market="global_developed",
        classification_set_id="wm_global_taxonomy_v1",
        classification_labels={
            "asset_class": "equity",
            "sector": "broad_market_equity",
            "region": "global",
        },
        effective_from=date(2026, 1, 1),
        effective_to=None,
        quality_status=quality_status,
        source_timestamp=datetime(2026, 4, 10, 9, tzinfo=UTC),
        source_vendor="MSCI",
        source_record_id="index:world:2026",
        created_at=datetime(2026, 4, 10, 8, tzinfo=UTC),
        updated_at=EVIDENCE_AT,
    )


def _build(definitions: list[IndexDefinitionEvidence], *, generated_at: datetime = GENERATED_AT):
    return build_index_catalog_response(
        request=REQUEST,
        definitions=definitions,
        generated_at=generated_at,
    )


def test_accepted_catalog_is_complete_current_and_deterministic() -> None:
    response = _build([_definition()])

    assert response.record_count == 1
    assert response.completeness_status == "COMPLETE"
    assert response.source_evidence_current is True
    assert response.freshness_status == "CURRENT"
    assert response.source_batch_fingerprint == response.content_hash == response.source_digest
    assert response.records[0].classification_labels["sector"] == "broad_market_equity"


def test_non_accepted_record_degrades_catalog() -> None:
    response = _build([_definition(quality_status="stale")])

    assert response.completeness_status == "PARTIAL"
    assert response.data_quality_status == "PARTIAL"
    assert response.source_evidence_current is False


def test_empty_catalog_is_truthfully_unavailable() -> None:
    response = _build([])

    assert response.record_count == 0
    assert response.completeness_status == "EMPTY"
    assert response.data_quality_status == "EMPTY"
    assert response.freshness_status == "UNAVAILABLE"


def test_content_hash_excludes_generated_at() -> None:
    first = _build([_definition()])
    second = _build(
        [_definition()],
        generated_at=datetime(2026, 4, 10, 13, tzinfo=UTC),
    )

    assert first.generated_at != second.generated_at
    assert first.content_hash == second.content_hash


@pytest.mark.asyncio
async def test_service_propagates_target_ids_and_filters() -> None:
    class Reader:
        async def list_definitions(self, **kwargs: object) -> list[IndexDefinitionEvidence]:
            self.kwargs = kwargs
            return [_definition()]

    reader = Reader()
    request = IndexCatalogRequest(
        as_of_date=date(2026, 4, 10),
        index_ids=["IDX_MSCI_WORLD_TR"],
        index_currency="usd",
        index_type="equity_index",
        index_status="active",
    )
    response = await IndexCatalogService(
        reader=reader,  # type: ignore[arg-type]
        clock=lambda: GENERATED_AT,
    ).list(request=request)

    assert reader.kwargs == {
        "as_of_date": date(2026, 4, 10),
        "index_ids": ["IDX_MSCI_WORLD_TR"],
        "index_currency": "usd",
        "index_type": "equity_index",
        "index_status": "active",
    }
    assert response.records[0].index_id == "IDX_MSCI_WORLD_TR"
