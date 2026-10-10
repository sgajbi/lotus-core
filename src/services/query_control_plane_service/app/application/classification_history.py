"""Qualify exact retained reference selections without current-state enrichment."""

from portfolio_common.api_contract.classification_history import (
    ClassificationHistoryEvidence,
    ClassificationHistorySelection,
    RetainedClassificationCut,
)
from portfolio_common.domain.reference_data.classification_history import (
    missing_assignment_coverage,
)
from portfolio_common.source_data_product_metadata import (
    SourceDataDegradationDetail,
    SourceDataDegradationSummary,
)


def selected_classification_history(
    selection: ClassificationHistorySelection, retained: RetainedClassificationCut | None
) -> ClassificationHistoryEvidence:
    reason = _selection_refusal(selection, retained)
    if reason is not None or retained is None:
        return ClassificationHistoryEvidence(
            status="UNAVAILABLE",
            selection=selection,
            reason_codes=(reason or "CLASSIFICATION_CUT_UNAVAILABLE",),
        )
    source = retained.source
    rows = tuple(
        row
        for row in source.assignments
        if row.effective_from < selection.until and row.effective_to > selection.period_start
    )
    missing = missing_assignment_coverage(
        [row.model_dump() for row in rows],
        securities=selection.expected_security_ids,
        start=selection.period_start,
        until=selection.until,
    )
    reasons = []
    if source.coverage_from > selection.period_start or source.coverage_to < selection.until:
        reasons.append("CLASSIFICATION_PERIOD_NOT_COVERED")
    if missing:
        reasons.append("CLASSIFICATION_ASSIGNMENT_COVERAGE_INCOMPLETE")
    return ClassificationHistoryEvidence(
        status="PARTIAL" if reasons else "COMPLETE",
        selection=selection,
        retained_cut=retained,
        assignments=rows,
        missing_security_ids=missing,
        reason_codes=tuple(reasons or ["CLASSIFICATION_DECLARED_UNIVERSE_COVERED"]),
    )


def _selection_refusal(
    selection: ClassificationHistorySelection, retained: RetainedClassificationCut | None
) -> str | None:
    if retained is None:
        return "CLASSIFICATION_CUT_UNAVAILABLE"
    source = retained.source
    if (
        (retained.cut_id, retained.content_hash) != (selection.cut_id, selection.content_hash)
        or any(
            getattr(source, name) != getattr(selection, name)
            for name in (
                "producer_id",
                "classification_set_id",
                "source_record_id",
                "source_version",
            )
        )
        or retained.received_at > selection.known_at
        or source.observed_at > selection.source_as_of
    ):
        return "CLASSIFICATION_SELECTION_UNAVAILABLE"
    if set(source.expected_security_ids) != set(selection.expected_security_ids) or set(
        source.expected_group_ids
    ) != set(selection.expected_group_ids):
        return "CLASSIFICATION_EXPECTED_UNIVERSE_MISMATCH"
    return None


def classification_history_degradation(
    history: ClassificationHistoryEvidence,
) -> SourceDataDegradationSummary:
    """Keep declared coverage separate from unavailable provider/joined authority."""
    reasons = {
        "SOURCE_PRODUCER_UNQUALIFIED": ["history.qualification"],
        "JOINED_SOURCE_CUT_COMPATIBILITY_UNPROVEN": ["history.compatibility"],
    }
    if history.status != "COMPLETE":
        reasons.update({reason: ["history.assignments"] for reason in history.reason_codes})
    return SourceDataDegradationSummary(
        status="UNAVAILABLE",
        reason_codes=sorted(reasons),
        details=[
            SourceDataDegradationDetail(
                section="history",
                affected_fields=reasons[reason],
                source_kind="UNAVAILABLE",
                source_product_name="InstrumentReferenceBundle",
                freshness_status="UNAVAILABLE",
                reason_code=reason,
            )
            for reason in sorted(reasons)
        ],
    )
