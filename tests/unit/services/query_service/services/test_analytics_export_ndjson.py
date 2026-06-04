from __future__ import annotations

import gzip
import json

import pytest

from src.services.query_service.app.services.analytics_export_ndjson import (
    AnalyticsExportNdjsonError,
    analytics_export_ndjson_result,
)


def test_analytics_export_ndjson_result_renders_metadata_and_records() -> None:
    result = analytics_export_ndjson_result(
        job_id="aexp_1",
        dataset_type="portfolio_timeseries",
        result_payload={
            "generated_at": "2026-03-01T00:00:00Z",
            "contract_version": "rfc_063_v1",
            "data": [{"valuation_date": "2025-01-01"}, {"valuation_date": "2025-01-02"}],
        },
        compression="none",
    )

    assert result.media_type == "application/x-ndjson"
    assert result.content_encoding == "none"
    lines = result.content.decode("utf-8").splitlines()
    assert json.loads(lines[0]) == {
        "record_type": "metadata",
        "job_id": "aexp_1",
        "dataset_type": "portfolio_timeseries",
        "generated_at": "2026-03-01T00:00:00Z",
        "contract_version": "rfc_063_v1",
    }
    assert json.loads(lines[1]) == {
        "record_type": "data",
        "record": {"valuation_date": "2025-01-01"},
    }
    assert json.loads(lines[2]) == {
        "record_type": "data",
        "record": {"valuation_date": "2025-01-02"},
    }


def test_analytics_export_ndjson_result_compresses_gzip_payload() -> None:
    result = analytics_export_ndjson_result(
        job_id="aexp_1",
        dataset_type="position_timeseries",
        result_payload={
            "generated_at": "2026-03-01T00:00:00Z",
            "contract_version": "rfc_063_v1",
            "data": [{"security_id": "SEC_1"}],
        },
        compression="gzip",
    )

    assert result.media_type == "application/x-ndjson"
    assert result.content_encoding == "gzip"
    assert b'"dataset_type":"position_timeseries"' in gzip.decompress(result.content)


def test_analytics_export_ndjson_result_rejects_malformed_data() -> None:
    with pytest.raises(AnalyticsExportNdjsonError, match="Export payload data is malformed"):
        analytics_export_ndjson_result(
            job_id="aexp_1",
            dataset_type="portfolio_timeseries",
            result_payload={"data": "bad"},
            compression="none",
        )
