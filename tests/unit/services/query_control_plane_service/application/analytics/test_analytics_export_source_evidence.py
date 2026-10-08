import gzip
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.query_control_plane_service.app.application.analytics.analytics_export_execution import (  # noqa: E501
    collect_portfolio_timeseries_for_export,
    collect_position_timeseries_for_export,
)
from src.services.query_control_plane_service.app.application.analytics.analytics_export_jobs import (  # noqa: E501
    analytics_export_result_payload,
    record_analytics_export_result_metrics,
)
from src.services.query_control_plane_service.app.application.analytics.analytics_export_results import (  # noqa: E501
    analytics_export_json_result_response,
    analytics_export_ndjson_result_response,
)
from src.services.query_control_plane_service.app.application.analytics.analytics_input_errors import (  # noqa: E501
    AnalyticsInputError,
)
from src.services.query_control_plane_service.app.contracts.analytics_inputs import (
    PortfolioAnalyticsTimeseriesRequest,
    PortfolioAnalyticsTimeseriesResponse,
    PositionAnalyticsTimeseriesRequest,
    PositionAnalyticsTimeseriesResponse,
)


def source_page(dataset, *, cut="cut-A", current=True, next_page=None, revision="r1"):
    values = dict(
        generated_at="2026-01-01T00:00:00Z",
        as_of_date="2025-12-31",
        portfolio_id="P1",
        portfolio_currency="EUR",
        reporting_currency="EUR",
        resolved_window={"start_date": "2025-12-01", "end_date": "2025-12-31"},
        frequency="daily",
        source_cut_id=cut,
        source_evidence_current=current,
        data_quality_status="COMPLETE" if current else "PARTIAL",
        freshness_status="CURRENT" if current else "STALE",
        restatement_version=revision,
        content_hash="sha256:" + "a" * 64,
        source_lineage={"content_hash_scope": "response_page", "cut_reason": "UNAVAILABLE"},
        lineage={
            "generated_by": "integration.analytics_inputs",
            "generated_at": "2026-01-01T00:00:00Z",
            "request_fingerprint": "scope-1",
            "data_version": "state_inputs_v1",
        },
        page={
            "page_size": 2000,
            "returned_row_count": 0,
            "sort_key": "valuation_date:asc",
            "request_scope_fingerprint": "scope-1",
            "snapshot_epoch": 1,
            "next_page_token": next_page,
        },
        diagnostics={},
    )
    if dataset == "portfolio":
        return PortfolioAnalyticsTimeseriesResponse(portfolio_open_date="2020-01-01", **values)
    return PositionAnalyticsTimeseriesResponse(**values)


async def collect(dataset, pages):
    getter = AsyncMock(side_effect=pages)
    if dataset == "portfolio":
        return await collect_portfolio_timeseries_for_export(
            portfolio_id="P1",
            request=PortfolioAnalyticsTimeseriesRequest(
                as_of_date="2025-12-31", period="one_month"
            ),
            get_portfolio_timeseries=getter,
        )
    return await collect_position_timeseries_for_export(
        portfolio_id="P1",
        request=PositionAnalyticsTimeseriesRequest(as_of_date="2025-12-31", period="one_month"),
        get_position_timeseries=getter,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("dataset", ["portfolio", "position"])
async def test_retains_ordered_evidence_and_degraded_second_page(dataset):
    result = await collect(
        dataset,
        [
            source_page(dataset, next_page="next"),
            source_page(dataset, current=False, revision="r2"),
        ],
    )
    manifest = result.source_evidence
    assert manifest.source_cut_id == "cut-A"
    assert manifest.source_cut_status == "AVAILABLE"
    assert manifest.source_evidence_current is False
    assert manifest.quality_statuses == ["COMPLETE", "PARTIAL"]
    assert manifest.freshness_statuses == ["CURRENT", "STALE"]
    assert [page.page_number for page in manifest.pages] == [1, 2]
    assert [page.source_metadata["restatement_version"] for page in manifest.pages] == ["r1", "r2"]
    assert (
        manifest.pages[0].source_metadata["source_lineage"]["content_hash_scope"] == "response_page"
    )
    assert manifest.pages[0].requested_scope["as_of_date"] == "2025-12-31"
    assert result.data_rows == []


@pytest.mark.asyncio
@pytest.mark.parametrize("dataset", ["portfolio", "position"])
async def test_mixed_known_cuts_refuse(dataset):
    with pytest.raises(AnalyticsInputError, match="source cuts"):
        await collect(
            dataset, [source_page(dataset, next_page="next"), source_page(dataset, cut="cut-B")]
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("dataset", ["portfolio", "position"])
@pytest.mark.parametrize("cuts", [(None, None), ("cut-A", None), ("UNAVAILABLE", "UNAVAILABLE")])
async def test_unknown_cut_is_not_upgraded_by_equal_hashes_or_completed_paging(dataset, cuts):
    result = await collect(
        dataset,
        [source_page(dataset, cut=cuts[0], next_page="next"), source_page(dataset, cut=cuts[1])],
    )
    assert result.source_evidence.source_cut_status == "UNAVAILABLE"
    assert result.source_evidence.source_cut_id is None
    assert "SOURCE_CUT_UNAVAILABLE" in result.source_evidence.unavailable_reasons


@pytest.mark.asyncio
@pytest.mark.parametrize("dataset", ["portfolio", "position"])
@pytest.mark.parametrize("degraded", [False, True])
async def test_retained_result_repeated_json_ndjson_agreement_without_new_source_reads(
    dataset, degraded
):
    pages = [source_page(dataset, next_page="next"), source_page(dataset, current=not degraded)]
    result = await collect(dataset, pages)
    dataset_type = f"{dataset}_timeseries"
    payload = analytics_export_result_payload(
        job_id="aexp_1162",
        dataset_type=dataset_type,
        request_fingerprint="fp",
        lifecycle_mode="inline_job_execution",
        data_rows=[{"amount": "123.4500"}],
        source_evidence=result.source_evidence,
    )
    retained = json.loads(json.dumps(payload))
    row = SimpleNamespace(
        job_id="aexp_1162", dataset_type=dataset_type, status="completed", result_payload=retained
    )
    # Later source revision cannot rewrite an existing result's acquired evidence.
    pages[0].restatement_version = "later-revision"
    expected = retained["source_evidence"]
    for _ in range(2):
        response = analytics_export_json_result_response(row)
        assert response.source_evidence.model_dump(mode="json") == expected
        assert response.data == [{"amount": "123.4500"}]
        for compression in ("none", "gzip"):
            data, _, _ = analytics_export_ndjson_result_response(row, compression=compression)
            if compression == "gzip":
                data = gzip.decompress(data)
            lines = [json.loads(line) for line in data.splitlines()]
            assert lines[0]["source_evidence"] == expected
            assert lines[1]["record"] == response.data[0]
    assert expected["pages"][0]["source_metadata"]["restatement_version"] == "r1"
    assert response.source_evidence.source_evidence_current is (not degraded)


def test_legacy_export_is_explicitly_unavailable_in_both_formats_without_payload_mutation():
    retained = dict(
        job_id="old",
        dataset_type="portfolio_timeseries",
        request_fingerprint="fp",
        lifecycle_mode="inline_job_execution",
        generated_at="2026-01-01T00:00:00Z",
        contract_version="rfc_063_v1",
        result_row_count=0,
        data=[],
    )
    row = SimpleNamespace(
        job_id="old",
        dataset_type="portfolio_timeseries",
        status="completed",
        result_payload=retained,
    )
    json_evidence = analytics_export_json_result_response(row).source_evidence
    data, _, _ = analytics_export_ndjson_result_response(row, compression="none")
    assert json.loads(data.splitlines()[0])["source_evidence"] == json_evidence.model_dump(
        mode="json"
    )
    assert json_evidence.availability == "UNAVAILABLE"
    assert json_evidence.pages == []
    assert json_evidence.unavailable_reasons == ["LEGACY_EXPORT_SOURCE_EVIDENCE_NOT_RETAINED"]
    assert "source_evidence" not in retained


@pytest.mark.asyncio
@pytest.mark.parametrize("contradiction", ["quality", "freshness", "degradation"])
async def test_contradictory_page_current_claim_does_not_hide_degradation(contradiction):
    page = source_page("position")
    if contradiction == "quality":
        page.data_quality_status = "PARTIAL"
    elif contradiction == "freshness":
        page.freshness_status = "STALE"
    else:
        page.degradation.status = "UNAVAILABLE"
    result = await collect("position", [page])
    assert result.source_evidence.source_evidence_current is False
    assert "PAGE_SOURCE_EVIDENCE_NOT_CURRENT" in result.source_evidence.unavailable_reasons


@pytest.mark.asyncio
async def test_result_byte_accounting_includes_retained_evidence(monkeypatch):
    from unittest.mock import MagicMock

    from src.services.query_control_plane_service.app.application.analytics import (
        analytics_export_jobs,
    )

    result = await collect("position", [source_page("position")])
    payload = analytics_export_result_payload(
        job_id="bytes",
        dataset_type="position_timeseries",
        request_fingerprint="fp",
        lifecycle_mode="inline_job_execution",
        data_rows=[],
        source_evidence=result.source_evidence,
    )
    metric = MagicMock()
    monkeypatch.setattr(analytics_export_jobs, "ANALYTICS_EXPORT_RESULT_BYTES", metric)
    record_analytics_export_result_metrics(
        result_format="json",
        compression="none",
        dataset_type="position_timeseries",
        result_payload=payload,
        page_depth=1,
    )
    expected_bytes = len(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    metric.labels.return_value.observe.assert_called_once_with(expected_bytes)
    without_evidence = {key: value for key, value in payload.items() if key != "source_evidence"}
    assert expected_bytes > len(json.dumps(without_evidence, separators=(",", ":")).encode("utf-8"))


@pytest.mark.asyncio
@pytest.mark.parametrize("dataset", ["portfolio", "position"])
async def test_conflicting_second_cut_refuses_before_fetching_third_page(dataset):
    getter = AsyncMock(
        side_effect=[
            source_page(dataset, next_page="second"),
            source_page(dataset, cut="cut-B", next_page="third"),
        ]
    )
    request_class = (
        PortfolioAnalyticsTimeseriesRequest
        if dataset == "portfolio"
        else PositionAnalyticsTimeseriesRequest
    )
    collector = (
        collect_portfolio_timeseries_for_export
        if dataset == "portfolio"
        else collect_position_timeseries_for_export
    )
    with pytest.raises(AnalyticsInputError, match="source cuts"):
        await collector(
            portfolio_id="P1",
            request=request_class(as_of_date="2025-12-31", period="one_month"),
            **{f"get_{dataset}_timeseries": getter},
        )
    assert getter.await_count == 2
