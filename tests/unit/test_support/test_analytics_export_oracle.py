"""Export proof must reject lost source facts, altered economics and format disagreement."""

import json
from copy import deepcopy

import pytest

from tests.test_support.analytics_export_oracle import (
    assert_corrected_export,
    assert_export_matches_source,
    assert_ndjson_matches_export,
)


def documents(dataset):
    request = {
        "as_of_date": "2026-04-10",
        "window": {"start_date": "2026-04-08", "end_date": "2026-04-10"},
    }
    metadata = {
        "product_name": "PortfolioTimeseriesInput"
        if dataset == "portfolio"
        else "PositionTimeseriesInput",
        "product_version": "v1",
        "portfolio_id": "SYNTHETIC",
        "portfolio_currency": "USD",
        "reporting_currency": "USD",
        "resolved_window": request["window"],
        "frequency": "daily",
        "contract_version": "rfc_063_v1",
        "data_quality_status": "COMPLETE",
        "freshness_status": "CURRENT",
        "source_evidence_current": True,
        "source_cut_id": None,
        "content_hash": "sha256:" + "a" * 64,
        "source_digest": "sha256:" + "a" * 64,
        "source_lineage": {
            "content_identity_scope": "response_page",
            "source_cut_status": "UNAVAILABLE",
        },
        "lineage": {"request_fingerprint": "retained-request"},
        "page": {"returned_row_count": 1, "next_page_token": None, "snapshot_epoch": 0},
    }
    rows = [{"valuation_date": "2026-04-10", "ending_market_value": "1200.00"}]
    source = {**deepcopy(metadata), "observations" if dataset == "portfolio" else "rows": rows}
    export = {
        "job_id": "synthetic-A",
        "dataset_type": f"{dataset}_timeseries",
        "generated_at": "2026-04-10T12:00:00Z",
        "contract_version": "rfc_063_v1",
        "result_row_count": 1,
        "data": deepcopy(rows),
        "source_evidence": {
            "manifest_version": "analytics_export_source_evidence_v1",
            "selection_digest": "sha256:" + "b" * 64,
            "availability": "RETAINED",
            "source_cut_status": "UNAVAILABLE",
            "source_cut_id": None,
            "source_evidence_current": True,
            "quality_statuses": ["COMPLETE"],
            "freshness_statuses": ["CURRENT"],
            "unavailable_reasons": ["SOURCE_CUT_UNAVAILABLE"],
            "pages": [
                {
                    "page_number": 1,
                    "row_count": 1,
                    "requested_scope": deepcopy(request),
                    "source_metadata": metadata,
                }
            ],
        },
    }
    return request, source, export


def ndjson(export):
    metadata = {
        key: export[key]
        for key in ("job_id", "dataset_type", "generated_at", "contract_version", "source_evidence")
    }
    return "\n".join(
        json.dumps(line)
        for line in [
            {"record_type": "metadata", **metadata},
            *[{"record_type": "data", "record": row} for row in export["data"]],
        ]
    ).encode()


@pytest.mark.parametrize("dataset", ["portfolio", "position"])
def test_complete_retained_export_and_ndjson_agree(dataset):
    request, source, export = documents(dataset)
    assert_export_matches_source(export, source, dataset, request)
    assert_ndjson_matches_export(ndjson(export), export)


@pytest.mark.parametrize("dataset", ["portfolio", "position"])
@pytest.mark.parametrize(
    "defect",
    [
        "rows",
        "count",
        "page_count",
        "request",
        "coverage",
        "page_rows",
        "page_identity",
        "cut",
        "degraded",
        "unavailable_reason",
        "digest",
        "missing_pages",
    ],
)
def test_incomplete_or_contradictory_retained_export_fails(dataset, defect):
    request, source, export = documents(dataset)
    evidence = export["source_evidence"]
    page = evidence["pages"][0]
    if defect == "rows":
        export["data"][0]["ending_market_value"] = "999"
    elif defect == "count":
        export["result_row_count"] = 0
    elif defect == "page_count":
        evidence["pages"].append(deepcopy(page))
    elif defect == "request":
        page["requested_scope"]["as_of_date"] = "2026-04-09"
    elif defect == "coverage":
        page["source_metadata"]["resolved_window"]["start_date"] = "2026-04-09"
    elif defect == "page_rows":
        page["row_count"] = 0
    elif defect == "page_identity":
        page["source_metadata"]["content_hash"] = "sha256:" + "c" * 64
    elif defect == "cut":
        evidence["source_cut_status"] = "AVAILABLE"
        evidence["source_cut_id"] = "invented-whole-cut"
    elif defect == "degraded":
        evidence["quality_statuses"] = ["PARTIAL"]
    elif defect == "unavailable_reason":
        evidence["unavailable_reasons"] = []
    elif defect == "digest":
        evidence["selection_digest"] = None
    else:
        evidence["pages"] = []
    with pytest.raises(AssertionError):
        assert_export_matches_source(export, source, dataset, request)


@pytest.mark.parametrize(
    "defect", ["metadata", "row", "missing", "extra", "key_missing", "key_extra"]
)
def test_ndjson_must_agree_with_complete_json(defect):
    _, _, export = documents("position")
    altered = deepcopy(export)
    if defect == "metadata":
        altered["source_evidence"]["source_evidence_current"] = False
    elif defect == "row":
        altered["data"][0]["ending_market_value"] = "0"
    elif defect == "missing":
        altered["data"] = []
    elif defect == "extra":
        altered["data"].append(deepcopy(altered["data"][0]))
    lines = [json.loads(line) for line in ndjson(altered).splitlines()]
    if defect == "key_missing":
        del lines[0]["source_evidence"]
    elif defect == "key_extra":
        lines[0]["unexpected"] = None
    document = "\n".join(json.dumps(line) for line in lines).encode()
    with pytest.raises(AssertionError):
        assert_ndjson_matches_export(document, export)


@pytest.mark.parametrize("dataset", ["portfolio", "position"])
@pytest.mark.parametrize("fraction", ["", ".867641"])
@pytest.mark.parametrize("suffixes", [("Z", "+00:00"), ("+00:00", "Z")])
def test_ndjson_generated_at_accepts_equivalent_utc_instants(dataset, fraction, suffixes):
    _, _, export = documents(dataset)
    wire = deepcopy(export)
    export["generated_at"] = f"2026-04-10T12:00:00{fraction}{suffixes[0]}"
    wire["generated_at"] = f"2026-04-10T12:00:00{fraction}{suffixes[1]}"
    assert_ndjson_matches_export(ndjson(wire), export)


@pytest.mark.parametrize(
    "timestamp",
    [
        "invalid",
        "2026-02-30T12:00:00Z",
        "2026-04-10T12:00:00",
        "2026-04-10T13:00:00+01:00",
        "2026-04-10T11:00:00-01:00",
        "2026-04-10T12:00:00.1234567Z",
        None,
    ],
)
@pytest.mark.parametrize("operand", ["json", "ndjson", "both"])
def test_ndjson_generated_at_refuses_invalid_operands_even_when_equal(timestamp, operand):
    _, _, export = documents("portfolio")
    wire = deepcopy(export)
    if operand in ("json", "both"):
        export["generated_at"] = timestamp
    if operand in ("ndjson", "both"):
        wire["generated_at"] = timestamp
    with pytest.raises(AssertionError):
        assert_ndjson_matches_export(ndjson(wire), export)


@pytest.mark.parametrize("timestamp", ["2026-04-10T12:00:01Z", "2026-04-10T12:00:00.000001+00:00"])
def test_ndjson_generated_at_refuses_different_instants(timestamp):
    _, _, export = documents("position")
    wire = deepcopy(export)
    wire["generated_at"] = timestamp
    with pytest.raises(AssertionError):
        assert_ndjson_matches_export(ndjson(wire), export)


@pytest.mark.parametrize("unchanged", ["job_id", "data", "digest", None])
def test_correction_requires_distinct_job_economics_and_selection(unchanged):
    _, _, original = documents("portfolio")
    corrected = deepcopy(original)
    corrected["job_id"] = "synthetic-B"
    corrected["data"][0]["ending_market_value"] = "1300"
    corrected["source_evidence"]["selection_digest"] = "sha256:" + "c" * 64
    if unchanged == "digest":
        corrected["source_evidence"]["selection_digest"] = original["source_evidence"][
            "selection_digest"
        ]
    elif unchanged is not None:
        corrected[unchanged] = original[unchanged]
    if unchanged is None:
        assert_corrected_export(original, corrected)
    else:
        with pytest.raises(AssertionError):
            assert_corrected_export(original, corrected)
