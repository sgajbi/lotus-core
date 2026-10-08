"""Conservative evidence retention, without creating source-cut authority."""

from ...contracts.analytics_export_evidence import (
    AnalyticsExportPageEvidence,
    AnalyticsExportSourceEvidence,
)
from ...contracts.analytics_inputs import (
    PortfolioAnalyticsTimeseriesRequest,
    PortfolioAnalyticsTimeseriesResponse,
    PositionAnalyticsTimeseriesRequest,
    PositionAnalyticsTimeseriesResponse,
)
from .analytics_input_errors import AnalyticsInputError


def export_page_evidence(
    *,
    response: PortfolioAnalyticsTimeseriesResponse | PositionAnalyticsTimeseriesResponse,
    request: PortfolioAnalyticsTimeseriesRequest | PositionAnalyticsTimeseriesRequest,
    page_number: int,
    row_count: int,
) -> AnalyticsExportPageEvidence:
    return AnalyticsExportPageEvidence(
        page_number=page_number,
        row_count=row_count,
        requested_scope=request.model_dump(mode="json", exclude={"page"}),
        source_metadata=response.model_dump(mode="json", exclude={"observations", "rows"}),
    )


def export_source_evidence(
    pages: list[AnalyticsExportPageEvidence],
) -> AnalyticsExportSourceEvidence:
    if not pages:
        return AnalyticsExportSourceEvidence()
    cuts = [page.source_metadata.get("source_cut_id") for page in pages]
    known_cuts = {cut for cut in cuts if isinstance(cut, str) and _known_cut(cut)}
    if len(known_cuts) > 1:
        raise AnalyticsInputError(
            "INSUFFICIENT_DATA", "Export pages contain conflicting source cuts."
        )
    cut_available = len(known_cuts) == 1 and all(cut in known_cuts for cut in cuts)
    current = all(_page_current(page.source_metadata) for page in pages)
    reasons = []
    if not cut_available:
        reasons.append("SOURCE_CUT_UNAVAILABLE")
    if not current:
        reasons.append("PAGE_SOURCE_EVIDENCE_NOT_CURRENT")
    return AnalyticsExportSourceEvidence(
        availability="RETAINED",
        source_cut_status="AVAILABLE" if cut_available else "UNAVAILABLE",
        source_cut_id=next(iter(known_cuts)) if cut_available else None,
        source_evidence_current=current,
        quality_statuses=_page_statuses(pages, "data_quality_status"),
        freshness_statuses=_page_statuses(pages, "freshness_status"),
        unavailable_reasons=reasons,
        pages=pages,
    )


def _page_statuses(pages: list[AnalyticsExportPageEvidence], field: str) -> list[str]:
    return list(
        dict.fromkeys(str(page.source_metadata.get(field) or "UNAVAILABLE") for page in pages)
    )


def retain_export_page(
    pages: list[AnalyticsExportPageEvidence],
    page: AnalyticsExportPageEvidence,
    known_cuts: set[str],
) -> None:
    cut = page.source_metadata.get("source_cut_id")
    if isinstance(cut, str) and _known_cut(cut):
        if known_cuts and cut not in known_cuts:
            raise AnalyticsInputError(
                "INSUFFICIENT_DATA", "Export pages contain conflicting source cuts."
            )
        known_cuts.add(cut)
    pages.append(page)


def _known_cut(cut: object) -> bool:
    return (
        isinstance(cut, str) and bool(cut.strip()) and cut.upper() not in {"UNKNOWN", "UNAVAILABLE"}
    )


def _page_current(metadata: dict[str, object]) -> bool:
    degradation = metadata.get("degradation")
    return (
        metadata.get("source_evidence_current") is True
        and metadata.get("data_quality_status") == "COMPLETE"
        and metadata.get("freshness_status") == "CURRENT"
        and isinstance(degradation, dict)
        and degradation.get("status") == "NONE"
        and not degradation.get("details")
    )
