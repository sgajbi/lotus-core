"""Fixed pre-extraction vector; only the original volatile fields remain excluded."""

from copy import deepcopy

import pytest
from portfolio_common.analytics_export_source_identity import export_source_selection_digest

pytestmark = pytest.mark.unit


def evidence():
    return {
        "selection_digest": None,
        "manifest_version": "analytics_export_source_evidence_v1",
        "availability": "RETAINED",
        "source_cut_status": "AVAILABLE",
        "source_cut_id": "cut",
        "source_evidence_current": True,
        "quality_statuses": ["COMPLETE"],
        "freshness_statuses": ["CURRENT"],
        "unavailable_reasons": [],
        "pages": [
            {
                "page_number": 1,
                "row_count": 1,
                "requested_scope": {"as_of_date": "2025-01-31"},
                "source_metadata": {
                    "tenant_id": "tenant",
                    "snapshot_epoch": 7,
                    "generated_at": "volatile",
                    "correlation_id": "volatile",
                    "lineage": {
                        "generated_at": "volatile",
                        "request_fingerprint": "volatile",
                        "snapshot_epoch": 7,
                    },
                    "page": {"next_page_token": "volatile", "returned_count": 1},
                },
            }
        ],
    }


def rows():
    return [{"valuation_date": "2025-01-31", "eod_market_value": "100.00"}]


def test_pre_extraction_fixed_vector_and_no_input_mutation():
    value = evidence()
    before = deepcopy(value)
    assert (
        export_source_selection_digest(rows(), value)
        == "sha256:a912b4ff2bcfe02e26f9c3d43a1d62892ec9098a3a5baf6c30ab3cc14bd712f9"
    )
    assert value == before


@pytest.mark.parametrize(
    "kind",
    [
        "generation",
        "correlation",
        "lineage_generation",
        "fingerprint",
        "continuation",
        "own_digest",
    ],
)
def test_only_original_volatile_exclusions_remain(kind):
    value = evidence()
    metadata = value["pages"][0]["source_metadata"]
    if kind == "generation":
        metadata["generated_at"] = "changed"
    elif kind == "correlation":
        metadata["correlation_id"] = "changed"
    elif kind == "lineage_generation":
        metadata["lineage"]["generated_at"] = "changed"
    elif kind == "fingerprint":
        metadata["lineage"]["request_fingerprint"] = "changed"
    elif kind == "continuation":
        metadata["page"]["next_page_token"] = "changed"
    else:
        value["selection_digest"] = "changed"
    assert export_source_selection_digest(rows(), value) == export_source_selection_digest(
        rows(), evidence()
    )


@pytest.mark.parametrize(
    "kind", ["row", "epoch", "lineage_epoch", "quality", "scope", "page_order", "unknown_metadata"]
)
def test_substantive_rows_epochs_evidence_scope_and_page_order_change_identity(kind):
    value, records = evidence(), rows()
    metadata = value["pages"][0]["source_metadata"]
    if kind == "row":
        records[0]["eod_market_value"] = "101.00"
    elif kind == "epoch":
        metadata["snapshot_epoch"] = 8
    elif kind == "lineage_epoch":
        metadata["lineage"]["snapshot_epoch"] = 8
    elif kind == "quality":
        value["quality_statuses"] = ["PARTIAL"]
    elif kind == "scope":
        value["pages"][0]["requested_scope"]["as_of_date"] = "2025-02-01"
    elif kind == "unknown_metadata":
        metadata["generated_at_elsewhere"] = "retained"
    else:
        other = deepcopy(value["pages"][0])
        other["page_number"] = 2
        original = deepcopy(value)
        original["pages"].append(other)
        value["pages"] = [other, value["pages"][0]]
        assert export_source_selection_digest(records, value) != export_source_selection_digest(
            records, original
        )
        return
    assert export_source_selection_digest(records, value) != export_source_selection_digest(
        rows(), evidence()
    )
