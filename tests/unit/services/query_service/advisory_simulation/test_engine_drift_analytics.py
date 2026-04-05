from decimal import Decimal

from src.services.query_service.app.advisory_simulation.common.drift_analytics import (
    compute_drift_analysis,
)
from src.services.query_service.app.advisory_simulation.models import (
    AllocationMetric,
    EngineOptions,
    Money,
    ReferenceAssetClassTarget,
    ReferenceInstrumentTarget,
    ReferenceModel,
    SimulatedState,
)


def _allocation(key: str, weight: str) -> AllocationMetric:
    return AllocationMetric(
        key=key,
        weight=Decimal(weight),
        value=Money(amount=Decimal("100"), currency="USD"),
    )


def _state(asset_allocations, instrument_allocations) -> SimulatedState:
    return SimulatedState(
        total_value=Money(amount=Decimal("1000"), currency="USD"),
        cash_balances=[],
        positions=[],
        allocation_by_asset_class=asset_allocations,
        allocation_by_instrument=instrument_allocations,
        allocation=instrument_allocations,
        allocation_by_attribute={},
    )


def test_compute_drift_analysis_asset_class_totals_and_ordering():
    before = _state(
        asset_allocations=[
            _allocation("EQUITY", "0.70"),
            _allocation("FIXED_INCOME", "0.20"),
            _allocation("CASH", "0.10"),
        ],
        instrument_allocations=[],
    )
    after = _state(
        asset_allocations=[
            _allocation("EQUITY", "0.62"),
            _allocation("FIXED_INCOME", "0.33"),
            _allocation("CASH", "0.05"),
        ],
        instrument_allocations=[],
    )
    reference_model = ReferenceModel(
        model_id="model_1",
        as_of="2026-02-18",
        base_currency="USD",
        asset_class_targets=[
            ReferenceAssetClassTarget(asset_class="EQUITY", weight=Decimal("0.60")),
            ReferenceAssetClassTarget(asset_class="FIXED_INCOME", weight=Decimal("0.35")),
            ReferenceAssetClassTarget(asset_class="CASH", weight=Decimal("0.05")),
        ],
    )

    analysis = compute_drift_analysis(
        before=before,
        after=after,
        reference_model=reference_model,
        traded_instruments=set(),
        options=EngineOptions(),
    )

    assert analysis.asset_class.drift_total_before == Decimal("0.15")
    assert analysis.asset_class.drift_total_after == Decimal("0.02")
    assert analysis.asset_class.drift_total_delta == Decimal("-0.13")
    assert [item.bucket for item in analysis.asset_class.top_contributors_before] == [
        "FIXED_INCOME",
        "EQUITY",
        "CASH",
    ]


def test_compute_drift_analysis_instrument_union_and_unmodeled_exposure():
    before = _state(
        asset_allocations=[_allocation("CASH", "1.0")],
        instrument_allocations=[
            _allocation("EQ_A", "0.70"),
            _allocation("EQ_B", "0.20"),
        ],
    )
    after = _state(
        asset_allocations=[_allocation("CASH", "1.0")],
        instrument_allocations=[
            _allocation("EQ_A", "0.50"),
            _allocation("EQ_B", "0.20"),
            _allocation("EQ_C", "0.25"),
        ],
    )
    reference_model = ReferenceModel(
        model_id="model_2",
        as_of="2026-02-18",
        base_currency="USD",
        asset_class_targets=[ReferenceAssetClassTarget(asset_class="CASH", weight=Decimal("1.0"))],
        instrument_targets=[
            ReferenceInstrumentTarget(instrument_id="EQ_A", weight=Decimal("0.40")),
            ReferenceInstrumentTarget(instrument_id="EQ_B", weight=Decimal("0.60")),
        ],
    )
    options = EngineOptions(
        enable_instrument_drift=True,
        drift_unmodeled_exposure_threshold=Decimal("0.10"),
        drift_top_contributors_limit=3,
    )

    analysis = compute_drift_analysis(
        before=before,
        after=after,
        reference_model=reference_model,
        traded_instruments={"EQ_C"},
        options=options,
    )

    assert analysis.instrument is not None
    assert analysis.instrument.drift_total_before == Decimal("0.35")
    assert analysis.instrument.drift_total_after == Decimal("0.375")
    assert analysis.highlights.unmodeled_exposures[0].bucket == "EQ_C"
    assert analysis.highlights.largest_deteriorations[0].bucket == "EQ_C"


def test_compute_drift_analysis_skips_instrument_dimension_when_disabled():
    before = _state(asset_allocations=[_allocation("CASH", "1.0")], instrument_allocations=[])
    after = _state(asset_allocations=[_allocation("CASH", "1.0")], instrument_allocations=[])
    reference_model = ReferenceModel(
        model_id="model_3",
        as_of="2026-02-18",
        base_currency="USD",
        asset_class_targets=[ReferenceAssetClassTarget(asset_class="CASH", weight=Decimal("1.0"))],
        instrument_targets=[ReferenceInstrumentTarget(instrument_id="EQ_A", weight=Decimal("1.0"))],
    )

    analysis = compute_drift_analysis(
        before=before,
        after=after,
        reference_model=reference_model,
        traded_instruments={"EQ_A"},
        options=EngineOptions(enable_instrument_drift=False),
    )

    assert analysis.instrument is None

