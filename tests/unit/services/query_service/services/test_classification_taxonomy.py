from datetime import UTC, date, datetime
from types import SimpleNamespace

from src.services.query_service.app.services.classification_taxonomy import (
    build_classification_taxonomy_response,
)


def test_build_classification_taxonomy_response_maps_entries_and_runtime_metadata() -> None:
    observed_at = datetime(2026, 1, 31, 9, 30, tzinfo=UTC)
    rows = [
        SimpleNamespace(
            classification_set_id="wm_global_taxonomy_v1",
            taxonomy_scope="index",
            dimension_name="sector",
            dimension_value="technology",
            dimension_description="Technology sector classification",
            effective_from=date(2025, 1, 1),
            effective_to=None,
            quality_status="accepted",
            observed_at=observed_at,
        )
    ]

    response = build_classification_taxonomy_response(
        as_of_date=date(2026, 1, 31),
        taxonomy_scope="index",
        rows=rows,
    )

    assert response.product_name == "InstrumentReferenceBundle"
    assert response.as_of_date == date(2026, 1, 31)
    assert response.taxonomy_version == "rfc_062_v1"
    assert response.request_fingerprint
    assert len(response.records) == 1
    assert response.records[0].classification_set_id == "wm_global_taxonomy_v1"
    assert response.records[0].taxonomy_scope == "index"
    assert response.records[0].dimension_name == "sector"
    assert response.records[0].dimension_value == "technology"
    assert response.records[0].dimension_description == "Technology sector classification"
    assert response.records[0].effective_from == date(2025, 1, 1)
    assert response.records[0].effective_to is None
    assert response.records[0].quality_status == "accepted"
    assert response.data_quality_status == "COMPLETE"
    assert response.latest_evidence_timestamp == observed_at
