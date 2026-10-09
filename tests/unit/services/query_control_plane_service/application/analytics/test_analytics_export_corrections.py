"""Correction intents retain old economics and retry the same acquired export."""

import gzip
import json
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from portfolio_common.request_fingerprints import request_fingerprint
from pydantic import ValidationError

from src.services.query_control_plane_service.app.application.analytics.analytics_export_corrections import (  # noqa: E501
    export_selection_digest,
)
from src.services.query_control_plane_service.app.application.analytics.analytics_export_execution import (  # noqa: E501
    AnalyticsExportDataset,
)
from src.services.query_control_plane_service.app.application.analytics.analytics_input_errors import (  # noqa: E501
    AnalyticsInputError,
)
from src.services.query_control_plane_service.app.application.analytics.analytics_timeseries_service import (  # noqa: E501
    AnalyticsRuntimePolicy,
    AnalyticsTimeseriesService,
)
from src.services.query_control_plane_service.app.contracts.analytics_export_evidence import (
    AnalyticsExportPageEvidence,
    AnalyticsExportSourceEvidence,
)
from src.services.query_control_plane_service.app.contracts.analytics_inputs import (
    AnalyticsExportCreateRequest,
)


class ExportMemoryStore:
    """Application test double, not database or ingestion qualification."""

    def __init__(self):
        self.rows = {}

    async def get_job(self, job_id):
        return self.rows.get(job_id)

    async def get_latest_by_fingerprint(self, *, request_fingerprint, dataset_type):
        return next(
            (
                row
                for row in reversed(list(self.rows.values()))
                if row.request_fingerprint == request_fingerprint
                and row.dataset_type == dataset_type
            ),
            None,
        )

    async def create_job(self, **fields):
        row = SimpleNamespace(
            **fields,
            status="accepted",
            result_payload=None,
            result_row_count=None,
            error_message=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            started_at=None,
            completed_at=None,
        )
        self.rows[row.job_id] = row
        return row

    async def mark_running(self, row):
        row.status = "running"
        return row

    async def mark_completed(self, row, *, result_payload, result_row_count):
        row.status = "completed"
        row.result_payload = json.loads(json.dumps(result_payload))
        row.result_row_count = result_row_count
        return row


class MemoryUnitOfWork:
    @asynccontextmanager
    async def transaction(self):
        yield


def service_and_request(dataset):
    store = ExportMemoryStore()
    service = AnalyticsTimeseriesService(
        reader=AsyncMock(),
        export_store=store,
        unit_of_work=MemoryUnitOfWork(),
        policy=AnalyticsRuntimePolicy(
            page_token_secret="local-test",
            page_token_key_id="test",
            page_token_previous_keys={},
            page_token_ttl_seconds=900,
            export_stale_timeout_minutes=15,
            export_execution_timeout_seconds=300,
        ),
    )
    request = AnalyticsExportCreateRequest.model_validate(
        {
            "dataset_type": dataset,
            "portfolio_id": "P1",
            f"{dataset}_request": {"as_of_date": "2025-12-31", "period": "one_month"},
        }
    )
    return service, store, request


def acquired(value, *, quality="COMPLETE"):
    return AnalyticsExportDataset(
        [{"eod_market_value": value}],
        1,
        AnalyticsExportSourceEvidence(
            availability="RETAINED",
            quality_statuses=[quality],
            pages=[
                AnalyticsExportPageEvidence(
                    page_number=1,
                    row_count=1,
                    requested_scope={"as_of_date": "2025-12-31"},
                    source_metadata={"data_quality_status": quality, "source_cut_id": None},
                )
            ],
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("dataset", ["portfolio_timeseries", "position_timeseries"])
@pytest.mark.parametrize("corrected_value,quality", [("120.00", "COMPLETE"), ("100.00", "PARTIAL")])
async def test_explicit_correction_retains_original_and_replays_each_intent(
    dataset, corrected_value, quality
):
    service, store, request = service_and_request(dataset)
    service._collect_export_dataset = AsyncMock(return_value=acquired("100.00"))
    original = await service.create_export_job(request)
    original_bytes = json.dumps(store.rows[original.job_id].result_payload, sort_keys=True)
    service._collect_export_dataset.return_value = acquired(corrected_value, quality=quality)
    assert (await service.create_export_job(request)).job_id == original.job_id

    correction = AnalyticsExportCreateRequest.model_validate(
        {
            **request.model_dump(mode="json"),
            "refresh_of_job_id": original.job_id,
        }
    )
    corrected = await service.create_export_job(correction)
    assert corrected.job_id != original.job_id
    assert corrected.request_fingerprint != original.request_fingerprint
    assert (await service.create_export_job(correction)).job_id == corrected.job_id
    assert (await service.create_export_job(request)).job_id == original.job_id
    assert service._collect_export_dataset.await_count == 2
    assert json.dumps(store.rows[original.job_id].result_payload, sort_keys=True) == original_bytes
    old = await service.get_export_result_json(original.job_id)
    new = await service.get_export_result_json(corrected.job_id)
    assert old.data == [{"eod_market_value": "100.00"}]
    assert new.data == [{"eod_market_value": corrected_value}]
    assert old.source_evidence.selection_digest != new.source_evidence.selection_digest
    assert new.source_evidence.source_cut_status == "UNAVAILABLE"
    assert new.source_evidence.source_cut_id is None
    for response in (old, new):
        for compression in ("none", "gzip"):
            payload, _, _ = await service.get_export_result_ndjson(
                response.job_id, compression=compression
            )
            if compression == "gzip":
                payload = gzip.decompress(payload)
            lines = [json.loads(line) for line in payload.splitlines()]
            assert lines[0]["source_evidence"] == response.source_evidence.model_dump(mode="json")
            assert [line["record"] for line in lines[1:]] == response.data


@pytest.mark.asyncio
async def test_default_request_keeps_legacy_fingerprint():
    service, _, request = service_and_request("portfolio_timeseries")
    service._collect_export_dataset = AsyncMock(return_value=acquired("100.00"))
    expected = request_fingerprint(request.model_dump(mode="json", exclude={"refresh_of_job_id"}))
    assert (await service.create_export_job(request)).request_fingerprint == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid",
    [
        "missing",
        "running",
        "portfolio_id",
        "consumer_system",
        "compression",
        "result_format",
        "dataset_type",
        "portfolio_timeseries_request",
    ],
)
async def test_correction_rejects_missing_incomplete_or_different_scope_before_acquisition(invalid):
    service, store, request = service_and_request("portfolio_timeseries")
    service._collect_export_dataset = AsyncMock(return_value=acquired("100.00"))
    original = await service.create_export_job(request)
    if invalid == "missing":
        store.rows.clear()
    elif invalid == "running":
        store.rows[original.job_id].status = "running"
    else:
        store.rows[original.job_id].request_payload[invalid] = "OTHER"
    correction = AnalyticsExportCreateRequest.model_validate(
        {
            **request.model_dump(mode="json"),
            "refresh_of_job_id": original.job_id,
        }
    )
    with pytest.raises(AnalyticsInputError):
        await service.create_export_job(correction)
    assert service._collect_export_dataset.await_count == 1
    assert len(store.rows) == (0 if invalid == "missing" else 1)


@pytest.mark.asyncio
async def test_correction_reuses_its_inflight_job_without_acquiring_again():
    service, store, request = service_and_request("portfolio_timeseries")
    service._collect_export_dataset = AsyncMock(return_value=acquired("100.00"))
    original = await service.create_export_job(request)
    correction = request.model_copy(update={"refresh_of_job_id": original.job_id})
    refreshed = await service.create_export_job(correction)
    store.rows[refreshed.job_id].status = "running"
    response = await service.create_export_job(correction)
    assert response.job_id == refreshed.job_id
    assert response.disposition == "reused_inflight"
    assert service._collect_export_dataset.await_count == 2


@pytest.mark.asyncio
async def test_further_correction_anchors_corrected_export_without_rewriting_either_intent():
    service, store, request = service_and_request("portfolio_timeseries")
    service._collect_export_dataset = AsyncMock(return_value=acquired("100.00"))
    first = await service.create_export_job(request)
    second_request = request.model_copy(update={"refresh_of_job_id": first.job_id})
    service._collect_export_dataset.return_value = acquired("120.00")
    second = await service.create_export_job(second_request)
    service._collect_export_dataset.return_value = acquired("140.00")
    assert (await service.create_export_job(second_request)).job_id == second.job_id
    third = await service.create_export_job(
        request.model_copy(update={"refresh_of_job_id": second.job_id})
    )
    assert len({first.job_id, second.job_id, third.job_id}) == 3
    assert [
        store.rows[job.job_id].result_payload["data"][0]["eod_market_value"]
        for job in (first, second, third)
    ] == ["100.00", "120.00", "140.00"]
    assert service._collect_export_dataset.await_count == 3


@pytest.mark.parametrize("invalid", ["", "random-intent", "aexp_" + "x" * 65])
def test_refresh_anchor_contract_refuses_non_job_id(invalid):
    _, _, request = service_and_request("portfolio_timeseries")
    with pytest.raises(ValidationError):
        AnalyticsExportCreateRequest.model_validate(
            {**request.model_dump(), "refresh_of_job_id": invalid}
        )


def test_selection_identity_excludes_serving_noise_but_preserves_source_facts():
    dataset = acquired("100.00")
    metadata = dataset.source_evidence.pages[0].source_metadata
    metadata.update(
        generated_at="clock-A",
        correlation_id="trace-A",
        lineage={"generated_at": "clock-A", "request_fingerprint": "token-A", "data_version": "v1"},
        page={"next_page_token": "token-A", "snapshot_epoch": 1},
    )
    expected = export_selection_digest(dataset)
    again = deepcopy(dataset)
    again.source_evidence.pages[0].source_metadata.update(
        generated_at="clock-B",
        correlation_id="trace-B",
        lineage={"generated_at": "clock-B", "request_fingerprint": "token-B", "data_version": "v1"},
        page={"next_page_token": "token-B", "snapshot_epoch": 1},
    )
    assert export_selection_digest(again) == expected
    assert metadata["generated_at"] == "clock-A"
    for field, value in (
        ("restatement_version", "corrected"),
        ("data_quality_status", "PARTIAL"),
        ("source_cut_id", "real-cut-B"),
    ):
        changed = deepcopy(dataset)
        changed.source_evidence.pages[0].source_metadata[field] = value
        assert export_selection_digest(changed) != expected
