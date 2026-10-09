"""Immutable correction intent and acquired export identity, not source-cut authority."""

from typing import cast

from portfolio_common.source_data_product_metadata import stable_content_hash

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
    pages = []
    for page in dataset.source_evidence.pages:
        metadata = dict(page.source_metadata)
        metadata.pop("generated_at", None)
        metadata.pop("correlation_id", None)
        lineage = metadata.get("lineage")
        if isinstance(lineage, dict):
            metadata["lineage"] = {
                key: value
                for key, value in lineage.items()
                if key not in {"generated_at", "request_fingerprint"}
            }
        paging = metadata.get("page")
        if isinstance(paging, dict):
            metadata["page"] = {
                key: value for key, value in paging.items() if key != "next_page_token"
            }
        pages.append({**page.model_dump(mode="json"), "source_metadata": metadata})
    return cast(
        str,
        stable_content_hash(
            {
                "identity_version": "analytics-export-selection-v1",
                "rows": dataset.data_rows,
                "source_evidence": dataset.source_evidence.model_dump(
                    mode="json", exclude={"pages", "selection_digest"}
                ),
                "pages": pages,
            }
        ),
    )
