"""Immutable correction intent and acquired export identity, not source-cut authority."""

from typing import cast

from portfolio_common.analytics_export_source_identity import export_source_selection_digest

from ...contracts.analytics_inputs import AnalyticsExportCreateRequest
from ...domain.analytics import AnalyticsExportJobRecord
from .analytics_export_execution import AnalyticsExportDataset
from .analytics_export_lifecycle import export_job_is_completed
from .analytics_input_errors import AnalyticsInputError


def export_request_payload(request: AnalyticsExportCreateRequest) -> dict[str, object]:
    # Preserve existing persisted request fingerprints when refresh is not requested.
    return cast(
        dict[str, object],
        request.model_dump(
            mode="json",
            exclude={"refresh_of_job_id"} if request.refresh_of_job_id is None else set(),
        ),
    )


def validate_export_refresh(
    original: AnalyticsExportJobRecord | None, request_payload: dict[str, object]
) -> None:
    if original is None:
        raise AnalyticsInputError("RESOURCE_NOT_FOUND", "Refresh export not found.")
    if not export_job_is_completed(original):
        raise AnalyticsInputError("INVALID_REQUEST", "Refresh requires a completed export.")
    original_basis = {
        key: value for key, value in original.request_payload.items() if key != "refresh_of_job_id"
    }
    new_basis = {key: value for key, value in request_payload.items() if key != "refresh_of_job_id"}
    if original_basis != new_basis:
        raise AnalyticsInputError(
            "INVALID_REQUEST", "Refresh must preserve the original export request."
        )


def export_selection_digest(dataset: AnalyticsExportDataset) -> str:
    return cast(
        str,
        export_source_selection_digest(
            dataset.data_rows, dataset.source_evidence.model_dump(mode="json")
        ),
    )
