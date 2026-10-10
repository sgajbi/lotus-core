"""Independent retained-export comparisons for supported correction evidence."""

import json
import re

from tests.test_support.analytics_correction_oracle import UNAVAILABLE, assert_content_identity


def assert_export_matches_source(export: dict, source: dict, dataset: str, request: dict) -> None:
    """Compare acquired economics and source facts, never manufacture whole-cut authority."""
    rows = source["observations" if dataset == "portfolio" else "rows"]
    assert export["dataset_type"] == f"{dataset}_timeseries"
    assert export["contract_version"] == "rfc_063_v1"
    assert export["result_row_count"] == len(rows)
    assert export["data"] == rows
    evidence = export["source_evidence"]
    assert evidence["manifest_version"] == "analytics_export_source_evidence_v1"
    assert evidence["availability"] == "RETAINED"
    assert evidence["source_cut_status"] == "UNAVAILABLE"
    assert evidence["source_cut_id"] is None
    assert evidence["source_evidence_current"] is True
    assert evidence["quality_statuses"] == ["COMPLETE"]
    assert evidence["freshness_statuses"] == ["CURRENT"]
    assert evidence["unavailable_reasons"] == ["SOURCE_CUT_UNAVAILABLE"]
    digest = evidence["selection_digest"]
    assert isinstance(digest, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
    assert digest != UNAVAILABLE
    # This fixture is below the unchanged 2,000-row export page bound. Multi-page,
    # empty and degraded policies are exercised separately by the owning PG cohort.
    assert len(evidence["pages"]) == 1
    page = evidence["pages"][0]
    assert page["page_number"] == 1
    assert page["row_count"] == len(rows)
    for key, value in request.items():
        if key != "page":
            assert page["requested_scope"][key] == value
    metadata = page["source_metadata"]
    assert "observations" not in metadata and "rows" not in metadata
    assert_content_identity(metadata)
    for key in (
        "product_name",
        "product_version",
        "portfolio_id",
        "portfolio_currency",
        "reporting_currency",
        "resolved_window",
        "frequency",
        "contract_version",
        "data_quality_status",
        "freshness_status",
        "source_evidence_current",
        "source_cut_id",
        "content_hash",
        "source_digest",
    ):
        assert metadata[key] == source[key]
    assert metadata["page"]["returned_row_count"] == len(rows)
    assert metadata["page"]["next_page_token"] is None
    assert metadata["page"]["snapshot_epoch"] == source["page"]["snapshot_epoch"]


def assert_ndjson_matches_export(document: bytes, export: dict) -> None:
    """Require the complete NDJSON metadata and every financial row to agree with JSON."""
    lines = [json.loads(line) for line in document.splitlines()]
    assert lines[0] == {
        "record_type": "metadata",
        "job_id": export["job_id"],
        "dataset_type": export["dataset_type"],
        "generated_at": export["generated_at"],
        "contract_version": export["contract_version"],
        "source_evidence": export["source_evidence"],
    }
    assert lines[1:] == [{"record_type": "data", "record": row} for row in export["data"]]


def assert_corrected_export(original: dict, corrected: dict) -> None:
    assert original["job_id"] != corrected["job_id"]
    assert original["data"] != corrected["data"]
    assert (
        original["source_evidence"]["selection_digest"]
        != corrected["source_evidence"]["selection_digest"]
    )
