"""Exact historical selection must not silently become a current taxonomy request."""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from portfolio_common.api_contract.classification_history import (
    CLASSIFICATION_CUT_EXAMPLE,
    CLASSIFICATION_SELECTION_EXAMPLE,
    ClassificationHistorySelection,
    InstrumentClassificationCut,
)
from portfolio_common.logging_utils import correlation_id_var
from pydantic import ValidationError

from src.services.ingestion_service.app.DTOs.reference_data_support_dto import (
    ClassificationTaxonomyIngestionRequest,
)
from src.services.query_control_plane_service.app.application.classification_history import (
    selected_classification_history,
)
from src.services.query_control_plane_service.app.application.classification_taxonomy import (
    ClassificationTaxonomyService,
)
from src.services.query_control_plane_service.app.contracts.classification_taxonomy import (
    ClassificationTaxonomyRequest,
)
from tests.test_support.classification_history import retained_cut, selection, source_cut


def test_taxonomy_request_retains_explicit_historical_selection():
    selection = {
        "producer_id": "SYNTHETIC_REFERENCE",
        "classification_set_id": "SYNTHETIC_SECTOR",
        "source_record_id": "SYNTHETIC_JANUARY",
        "source_version": 1,
        "cut_id": "sha256:" + "a" * 64,
        "content_hash": "sha256:" + "b" * 64,
        "period_start": "2026-01-01",
        "period_end": "2026-01-31",
        "source_as_of": "2026-02-01T00:00:00Z",
        "known_at": "2026-10-10T00:00:00Z",
        "expected_security_ids": ["SYNTHETIC_A", "SYNTHETIC_B"],
        "expected_group_ids": ["TECHNOLOGY", "FINANCE"],
    }
    request = ClassificationTaxonomyRequest.model_validate(
        {"as_of_date": "2026-01-31", "history_selection": selection}
    )
    assert request.model_dump(mode="json")["history_selection"] == selection


def test_complete_declared_universe_does_not_assert_financial_or_provider_authority():
    cut = retained_cut()
    evidence = selected_classification_history(selection(cut), cut)
    assert evidence.status == "COMPLETE"
    assert evidence.assignments == cut.source.assignments
    assert evidence.qualification == "RETAINED_UNQUALIFIED"
    assert evidence.compatibility == "UNAVAILABLE"


@pytest.mark.parametrize(
    "changes",
    [
        {"producer_id": "FOREIGN"},
        {"classification_set_id": "FOREIGN"},
        {"source_record_id": "FOREIGN"},
        {"source_version": 2},
        {"cut_id": "sha256:" + "0" * 64},
        {"content_hash": "sha256:" + "0" * 64},
        {"source_as_of": "2026-01-31T00:00:00Z"},
        {"known_at": "2026-02-01T12:00:00Z"},
        {"expected_security_ids": ["SYNTHETIC_A"]},
        {"expected_group_ids": ["FINANCE"]},
    ],
)
def test_unavailable_selection_never_falls_back(changes):
    cut = retained_cut()
    evidence = selected_classification_history(selection(cut, **changes), cut)
    assert evidence.status == "UNAVAILABLE"
    assert not evidence.assignments
    assert evidence.retained_cut is None


def test_omitted_security_is_partial_even_when_other_security_has_history():
    source = source_cut()
    cut = retained_cut(source_cut(assignments=[source.assignments[0].model_dump(mode="json")]))
    evidence = selected_classification_history(selection(cut), cut)
    assert evidence.status == "PARTIAL"
    assert evidence.missing_security_ids == ("SYNTHETIC_B",)


def test_adjacent_reclassification_and_correction_preserve_original_cut():
    original = source_cut()
    rows = [row.model_dump(mode="json") for row in original.assignments]
    rows[0]["effective_to"] = "2026-01-16"
    rows.append(
        rows[0]
        | {
            "group_id": "FINANCE",
            "effective_from": "2026-01-16",
            "effective_to": "2026-02-01",
            "source_record_id": "SYNTHETIC_RECLASS",
        }
    )
    cut = retained_cut(source_cut(assignments=rows))
    evidence = selected_classification_history(selection(cut), cut)
    assert evidence.status == "COMPLETE"
    assert len(evidence.assignments) == 3
    reordered = source_cut(assignments=list(reversed(rows)))
    assert reordered.identity() == cut.source.identity()
    corrected = source_cut(source_version=2, predecessor_cut_id=cut.cut_id, assignments=rows)
    assert corrected.identity() != cut.source.identity()
    assert selected_classification_history(selection(cut), cut) == evidence


@pytest.mark.parametrize(
    "changes",
    [
        {"security_id": "FOREIGN"},
        {"group_id": "FOREIGN"},
        {"effective_from": "2025-12-31"},
        {"effective_to": "2026-03-01"},
        {"observed_at": "2026-02-02T00:00:00Z"},
    ],
)
def test_source_rows_outside_declared_scope_refuse(changes):
    rows = [row.model_dump(mode="json") for row in source_cut().assignments]
    rows[0].update(changes)
    with pytest.raises(ValidationError):
        source_cut(assignments=rows)


def test_conflicting_assignment_intervals_refuse():
    rows = [row.model_dump(mode="json") for row in source_cut().assignments]
    rows.append(rows[0] | {"group_id": "FINANCE"})
    with pytest.raises(ValidationError, match="intervals conflict"):
        source_cut(assignments=rows)


def test_ingestion_mode_is_explicit_and_historical_receipt_round_trips():
    payload = {"assignment_cut": source_cut().model_dump(mode="json")}
    request = ClassificationTaxonomyIngestionRequest.model_validate(payload)
    assert (
        ClassificationTaxonomyIngestionRequest.model_validate(request.model_dump(mode="json"))
        == request
    )
    with pytest.raises(ValidationError):
        ClassificationTaxonomyIngestionRequest.model_validate({})
    with pytest.raises(ValidationError):
        source_cut(source_version=True)


@pytest.mark.asyncio
async def test_full_historical_serializer_matches_verified_catalog_without_legacy_read():
    root = next(
        parent
        for parent in Path(__file__).resolve().parents
        if (parent / "pyproject.toml").is_file()
    )
    catalog_path = root / "docs/standards/verified-api-examples.v1.json"
    example = next(
        item
        for item in json.loads(catalog_path.read_text(encoding="utf-8"))["examples"]
        if item["id"] == "historical-classification-custody"
    )
    reader = AsyncMock()
    reader.load_cut.return_value = retained_cut()
    request = ClassificationTaxonomyRequest.model_validate(example["request"]["body"])
    token = correlation_id_var.set("synthetic-correlation")
    try:
        response = await ClassificationTaxonomyService(
            reader=reader, clock=lambda: datetime(2026, 10, 10, tzinfo=UTC)
        ).get(request=request)
    finally:
        correlation_id_var.reset(token)
    assert response.model_dump(mode="json") == example["response"]["body"]
    reader.load_cut.assert_awaited_once_with(request.history_selection)
    reader.list_effective.assert_not_awaited()


def test_gap_and_half_open_boundary_cannot_be_silently_filled():
    rows = [row.model_dump(mode="json") for row in source_cut().assignments]
    rows[0]["effective_to"] = "2026-01-15"
    rows.append(rows[0] | {"effective_from": "2026-01-16", "effective_to": "2026-02-01"})
    cut = retained_cut(source_cut(assignments=rows))
    assert selected_classification_history(selection(cut), cut).missing_security_ids == (
        "SYNTHETIC_A",
    )
    covered = selection(cut, period_end="2026-01-14")
    gap = selection(cut, period_start="2026-01-15", period_end="2026-01-15")
    after = selection(cut, period_start="2026-01-16")
    assert selected_classification_history(covered, cut).status == "COMPLETE"
    assert selected_classification_history(gap, cut).status == "PARTIAL"
    assert selected_classification_history(after, cut).status == "COMPLETE"


def test_cut_identity_and_source_receipt_time_must_validate_before_selection():
    cut = retained_cut()
    for changes in (
        {"content_hash": "sha256:" + "0" * 64},
        {"received_at": "2026-01-01T00:00:00Z"},
    ):
        with pytest.raises(ValidationError):
            type(cut).model_validate(cut.model_dump(mode="json") | changes)


def test_published_request_examples_validate_and_select_their_actual_content_identity():
    source = InstrumentClassificationCut.model_validate(CLASSIFICATION_CUT_EXAMPLE)
    selected = ClassificationHistorySelection.model_validate(CLASSIFICATION_SELECTION_EXAMPLE)
    assert (selected.cut_id, selected.content_hash) == source.identity()
    assert selected_classification_history(selected, retained_cut(source)).status == "COMPLETE"
    request = ClassificationTaxonomyIngestionRequest.model_validate({"assignment_cut": source})
    assert request.assignment_cut == source
    for model in (ClassificationTaxonomyIngestionRequest, ClassificationTaxonomyRequest):
        for example in model.model_json_schema()["examples"]:
            model.model_validate(example)
    with pytest.raises(ValidationError, match="either taxonomy rows"):
        ClassificationTaxonomyIngestionRequest.model_validate(
            {
                "assignment_cut": source,
                "classification_taxonomy": [
                    {
                        "classification_set_id": "SYNTHETIC_SECTOR",
                        "taxonomy_scope": "instrument",
                        "dimension_name": "sector",
                        "dimension_value": "TECHNOLOGY",
                        "effective_from": "2026-01-01",
                    }
                ],
            }
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"expected_security_ids": ["SYNTHETIC_A", "SYNTHETIC_A"]},
        {"expected_group_ids": ["TECHNOLOGY", "TECHNOLOGY"]},
        {"coverage_to": "2026-01-01"},
        {"generated_at": "2026-01-31T00:00:00Z"},
        {"observed_at": "2026-02-01T00:00:00"},
        {"source_version": 2},
        {"predecessor_cut_id": "sha256:" + "0" * 64},
        {"assignments": []},
        {"current_labels": {}},
    ],
)
def test_invalid_source_scope_or_implicit_current_mode_refuses(changes):
    with pytest.raises(ValidationError):
        source_cut(**changes)


def test_serialized_cut_byte_limit_refuses_otherwise_valid_large_history():
    row = source_cut().assignments[0].model_dump(mode="json")
    start = date(2020, 1, 1)
    rows = [
        row
        | {
            "effective_from": (start + timedelta(days=index)).isoformat(),
            "effective_to": (start + timedelta(days=index + 1)).isoformat(),
            "source_record_id": "S" * 128,
        }
        for index in range(2000)
    ]
    with pytest.raises(ValidationError, match="CLASSIFICATION_CUT_TOO_LARGE"):
        source_cut(coverage_from="2020-01-01", assignments=rows)
