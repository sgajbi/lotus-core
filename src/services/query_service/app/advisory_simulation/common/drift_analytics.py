from collections.abc import Iterable, Sequence
from decimal import Decimal

from src.services.query_service.app.advisory_simulation.models import (
    AllocationMetric,
    DriftAnalysis,
    DriftBucketDetail,
    DriftDimensionAnalysis,
    DriftHighlightEntry,
    DriftHighlights,
    DriftReferenceModelSummary,
    DriftUnmodeledExposure,
    EngineOptions,
    ReferenceAssetClassTarget,
    ReferenceInstrumentTarget,
    ReferenceModel,
    SimulatedState,
)


def _to_weight_map(allocations: Sequence[AllocationMetric]) -> dict[str, Decimal]:
    return {allocation.key: allocation.weight for allocation in allocations}


def _to_asset_class_target_map(targets: Sequence[ReferenceAssetClassTarget]) -> dict[str, Decimal]:
    return {target.asset_class: target.weight for target in targets}


def _to_instrument_target_map(targets: Sequence[ReferenceInstrumentTarget]) -> dict[str, Decimal]:
    return {target.instrument_id: target.weight for target in targets}


def _build_dimension(
    *,
    before_weights: dict[str, Decimal],
    after_weights: dict[str, Decimal],
    model_weights: dict[str, Decimal],
    buckets: Iterable[str],
    top_limit: int,
) -> DriftDimensionAnalysis:
    details: list[DriftBucketDetail] = []
    for bucket in sorted(set(buckets)):
        model_weight = model_weights.get(bucket, Decimal("0"))
        before_weight = before_weights.get(bucket, Decimal("0"))
        after_weight = after_weights.get(bucket, Decimal("0"))
        drift_before = before_weight - model_weight
        drift_after = after_weight - model_weight
        abs_before = abs(drift_before)
        abs_after = abs(drift_after)
        details.append(
            DriftBucketDetail(
                bucket=bucket,
                model_weight=model_weight,
                portfolio_weight_before=before_weight,
                portfolio_weight_after=after_weight,
                drift_before=drift_before,
                drift_after=drift_after,
                abs_drift_before=abs_before,
                abs_drift_after=abs_after,
                improvement=abs_before - abs_after,
            )
        )

    drift_total_before = Decimal("0.5") * sum((d.abs_drift_before for d in details), Decimal("0"))
    drift_total_after = Decimal("0.5") * sum((d.abs_drift_after for d in details), Decimal("0"))
    top_contributors_before = sorted(
        details,
        key=lambda detail: (-detail.abs_drift_before, detail.bucket),
    )[:top_limit]

    return DriftDimensionAnalysis(
        drift_total_before=drift_total_before,
        drift_total_after=drift_total_after,
        drift_total_delta=drift_total_after - drift_total_before,
        top_contributors_before=top_contributors_before,
        buckets=details,
    )


def _build_highlights(
    *,
    details: list[DriftBucketDetail],
    top_limit: int,
    unmodeled_threshold: Decimal,
) -> DriftHighlights:
    improvements = sorted(
        [detail for detail in details if detail.improvement > 0],
        key=lambda detail: (-detail.improvement, detail.bucket),
    )[:top_limit]
    deteriorations = sorted(
        [detail for detail in details if detail.improvement < 0],
        key=lambda detail: (detail.improvement, detail.bucket),
    )[:top_limit]
    unmodeled = sorted(
        [
            detail
            for detail in details
            if detail.model_weight == 0
            and max(detail.portfolio_weight_before, detail.portfolio_weight_after)
            >= unmodeled_threshold
        ],
        key=lambda detail: (
            -max(detail.portfolio_weight_before, detail.portfolio_weight_after),
            detail.bucket,
        ),
    )[:top_limit]

    return DriftHighlights(
        largest_improvements=[
            DriftHighlightEntry(bucket=detail.bucket, improvement=detail.improvement)
            for detail in improvements
        ],
        largest_deteriorations=[
            DriftHighlightEntry(bucket=detail.bucket, improvement=detail.improvement)
            for detail in deteriorations
        ],
        unmodeled_exposures=[
            DriftUnmodeledExposure(
                bucket=detail.bucket,
                portfolio_weight_before=detail.portfolio_weight_before,
                portfolio_weight_after=detail.portfolio_weight_after,
                max_portfolio_weight=max(
                    detail.portfolio_weight_before,
                    detail.portfolio_weight_after,
                ),
            )
            for detail in unmodeled
        ],
    )


def compute_drift_analysis(
    *,
    before: SimulatedState,
    after: SimulatedState,
    reference_model: ReferenceModel,
    traded_instruments: set[str],
    options: EngineOptions,
) -> DriftAnalysis:
    before_by_asset_class = _to_weight_map(before.allocation_by_asset_class)
    after_by_asset_class = _to_weight_map(after.allocation_by_asset_class)
    model_by_asset_class = _to_asset_class_target_map(reference_model.asset_class_targets)
    asset_class_buckets = (
        set(before_by_asset_class.keys())
        | set(after_by_asset_class.keys())
        | set(model_by_asset_class.keys())
        | {"CASH"}
    )
    asset_class = _build_dimension(
        before_weights=before_by_asset_class,
        after_weights=after_by_asset_class,
        model_weights=model_by_asset_class,
        buckets=asset_class_buckets,
        top_limit=options.drift_top_contributors_limit,
    )

    instrument = None
    details_for_highlights = asset_class.buckets
    if options.enable_instrument_drift and reference_model.instrument_targets:
        before_by_instrument = _to_weight_map(before.allocation_by_instrument)
        after_by_instrument = _to_weight_map(after.allocation_by_instrument)
        model_by_instrument = _to_instrument_target_map(reference_model.instrument_targets)
        instrument_buckets = (
            set(before_by_instrument.keys())
            | set(after_by_instrument.keys())
            | set(model_by_instrument.keys())
            | set(traded_instruments)
        )
        instrument = _build_dimension(
            before_weights=before_by_instrument,
            after_weights=after_by_instrument,
            model_weights=model_by_instrument,
            buckets=instrument_buckets,
            top_limit=options.drift_top_contributors_limit,
        )
        details_for_highlights = instrument.buckets

    highlights = _build_highlights(
        details=details_for_highlights,
        top_limit=options.drift_top_contributors_limit,
        unmodeled_threshold=options.drift_unmodeled_exposure_threshold,
    )

    return DriftAnalysis(
        reference_model=DriftReferenceModelSummary(
            model_id=reference_model.model_id,
            as_of=reference_model.as_of,
            base_currency=reference_model.base_currency,
        ),
        asset_class=asset_class,
        instrument=instrument,
        highlights=highlights,
    )
