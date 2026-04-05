from decimal import Decimal

from src.services.query_service.app.advisory_simulation.common.suitability import (
    compute_suitability_result,
)
from src.services.query_service.app.advisory_simulation.models import (
    AllocationMetric,
    EngineOptions,
    Money,
    ShelfEntry,
    SimulatedState,
)


def _metric(key: str, weight: str) -> AllocationMetric:
    return AllocationMetric(
        key=key,
        weight=Decimal(weight),
        value=Money(amount=Decimal("100"), currency="USD"),
    )


def _state(*, instrument_weights: dict[str, str], cash_weight: str = "0.05") -> SimulatedState:
    non_cash_weight = Decimal("1") - Decimal(cash_weight)
    return SimulatedState(
        total_value=Money(amount=Decimal("1000"), currency="USD"),
        cash_balances=[],
        positions=[],
        allocation_by_asset_class=[
            _metric("EQUITY", str(non_cash_weight)),
            _metric("CASH", cash_weight),
        ],
        allocation_by_instrument=[
            _metric(instrument_id, weight)
            for instrument_id, weight in sorted(instrument_weights.items())
        ],
        allocation=[
            _metric(instrument_id, weight)
            for instrument_id, weight in sorted(instrument_weights.items())
        ],
        allocation_by_attribute={},
    )


def test_suitability_classifies_single_position_as_resolved():
    before = _state(instrument_weights={"EQ_A": "0.30", "EQ_B": "0.70"})
    after = _state(instrument_weights={"EQ_A": "0.08", "EQ_B": "0.92"})
    options = EngineOptions(
        suitability_thresholds={
            "single_position_max_weight": "0.10",
            "issuer_max_weight": "1.00",
            "max_weight_by_liquidity_tier": {},
            "cash_band_min_weight": "0",
            "cash_band_max_weight": "1",
        }
    )

    result = compute_suitability_result(
        before=before,
        after=after,
        shelf=[
            ShelfEntry(
                instrument_id="EQ_A",
                status="APPROVED",
                issuer_id="ISS_A",
                liquidity_tier="L1",
            ),
            ShelfEntry(
                instrument_id="EQ_B",
                status="APPROVED",
                issuer_id="ISS_B",
                liquidity_tier="L1",
            ),
        ],
        options=options,
        portfolio_snapshot_id="pf_1",
        market_data_snapshot_id="md_1",
    )

    assert result.summary.new_count == 0
    assert result.summary.resolved_count == 1
    assert result.summary.persistent_count == 1
    assert result.recommended_gate == "NONE"
    assert result.issues[0].issue_key == "SINGLE_POSITION_MAX|EQ_B"
    assert result.issues[0].status_change == "PERSISTENT"
    assert result.issues[1].issue_key == "SINGLE_POSITION_MAX|EQ_A"
    assert result.issues[1].status_change == "RESOLVED"


def test_suitability_detects_new_issuer_breach_and_recommends_compliance_review():
    before = _state(instrument_weights={"EQ_A": "0.10", "EQ_B": "0.90"})
    after = _state(instrument_weights={"EQ_A": "0.15", "EQ_B": "0.74", "EQ_C": "0.11"})
    options = EngineOptions(
        suitability_thresholds={
            "single_position_max_weight": "1.00",
            "issuer_max_weight": "0.20",
            "max_weight_by_liquidity_tier": {},
            "cash_band_min_weight": "0",
            "cash_band_max_weight": "1",
        }
    )

    result = compute_suitability_result(
        before=before,
        after=after,
        shelf=[
            ShelfEntry(
                instrument_id="EQ_A",
                status="APPROVED",
                issuer_id="ISS_SHARED",
                liquidity_tier="L1",
            ),
            ShelfEntry(
                instrument_id="EQ_B",
                status="APPROVED",
                issuer_id="ISS_B",
                liquidity_tier="L1",
            ),
            ShelfEntry(
                instrument_id="EQ_C",
                status="APPROVED",
                issuer_id="ISS_SHARED",
                liquidity_tier="L1",
            ),
        ],
        options=options,
        portfolio_snapshot_id="pf_1",
        market_data_snapshot_id="md_1",
    )

    assert result.summary.new_count == 1
    assert result.summary.highest_severity_new == "HIGH"
    assert result.recommended_gate == "COMPLIANCE_REVIEW"
    assert result.issues[0].issue_id == "SUIT_ISSUER_MAX"
    assert result.issues[0].status_change == "NEW"


def test_suitability_detects_sell_only_increase_as_new_high_issue():
    before = _state(instrument_weights={"EQ_SO": "0.10", "EQ_B": "0.90"})
    after = _state(instrument_weights={"EQ_SO": "0.15", "EQ_B": "0.85"})
    options = EngineOptions(
        suitability_thresholds={
            "single_position_max_weight": "1.00",
            "issuer_max_weight": "1.00",
            "max_weight_by_liquidity_tier": {},
            "cash_band_min_weight": "0",
            "cash_band_max_weight": "1",
        }
    )

    result = compute_suitability_result(
        before=before,
        after=after,
        shelf=[
            ShelfEntry(
                instrument_id="EQ_SO",
                status="SELL_ONLY",
                issuer_id="ISS_SO",
                liquidity_tier="L2",
            ),
            ShelfEntry(
                instrument_id="EQ_B",
                status="APPROVED",
                issuer_id="ISS_B",
                liquidity_tier="L1",
            ),
        ],
        options=options,
        portfolio_snapshot_id="pf_1",
        market_data_snapshot_id="md_1",
    )

    assert result.summary.new_count == 1
    assert result.recommended_gate == "COMPLIANCE_REVIEW"
    assert result.issues[0].issue_id == "SUIT_GOVERNANCE_SELL_ONLY_INCREASE"
    assert result.issues[0].status_change == "NEW"


def test_suitability_emits_data_quality_issues_with_configured_severity_and_ordering():
    before = _state(instrument_weights={"EQ_A": "0.20", "EQ_B": "0.80"}, cash_weight="0.20")
    after = _state(instrument_weights={"EQ_A": "0.20", "EQ_B": "0.80"}, cash_weight="0.20")
    options = EngineOptions(
        suitability_thresholds={
            "single_position_max_weight": "1.00",
            "issuer_max_weight": "1.00",
            "max_weight_by_liquidity_tier": {"L4": "0.10"},
            "cash_band_min_weight": "0.01",
            "cash_band_max_weight": "0.05",
            "data_quality_issue_severity": "HIGH",
        }
    )

    result = compute_suitability_result(
        before=before,
        after=after,
        shelf=[
            ShelfEntry(instrument_id="EQ_A", status="APPROVED"),
            ShelfEntry(
                instrument_id="EQ_B",
                status="APPROVED",
                issuer_id="ISS_B",
                liquidity_tier="L1",
            ),
        ],
        options=options,
        portfolio_snapshot_id="pf_1",
        market_data_snapshot_id="md_1",
    )

    assert result.summary.new_count == 0
    assert result.summary.persistent_count == 3
    assert result.summary.resolved_count == 0
    assert result.issues[0].status_change == "PERSISTENT"
    assert result.issues[0].severity == "HIGH"
    assert result.issues[0].issue_key == "DQ|MISSING_ISSUER|EQ_A"
    assert result.issues[1].issue_key == "DQ|MISSING_LIQUIDITY_TIER|EQ_A"


def test_suitability_covers_governance_liquidity_and_missing_shelf_paths():
    before = _state(instrument_weights={}, cash_weight="1.0")
    after = _state(
        instrument_weights={
            "EQ_BANNED": "0.10",
            "EQ_SUSPENDED": "0.10",
            "EQ_RESTRICTED": "0.10",
            "EQ_L4": "0.20",
            "EQ_MISSING_SHELF": "0.05",
        },
        cash_weight="0.45",
    )
    options = EngineOptions(
        allow_restricted=True,
        suitability_thresholds={
            "single_position_max_weight": "1.00",
            "issuer_max_weight": "1.00",
            "max_weight_by_liquidity_tier": {"L4": "0.10"},
            "cash_band_min_weight": "0",
            "cash_band_max_weight": "1",
            "data_quality_issue_severity": "LOW",
        },
    )

    result = compute_suitability_result(
        before=before,
        after=after,
        shelf=[
            ShelfEntry(
                instrument_id="EQ_BANNED",
                status="BANNED",
                issuer_id="ISS_B",
                liquidity_tier="L1",
            ),
            ShelfEntry(
                instrument_id="EQ_SUSPENDED",
                status="SUSPENDED",
                issuer_id="ISS_S",
                liquidity_tier="L1",
            ),
            ShelfEntry(
                instrument_id="EQ_RESTRICTED",
                status="RESTRICTED",
                issuer_id="ISS_R",
                liquidity_tier="L1",
            ),
            ShelfEntry(
                instrument_id="EQ_L4",
                status="APPROVED",
                issuer_id="ISS_L4",
                liquidity_tier="L4",
            ),
        ],
        options=options,
        portfolio_snapshot_id="pf_2",
        market_data_snapshot_id="md_2",
        proposed_trades=[
            {"side": "BUY", "instrument_id": "EQ_RESTRICTED"},
            {"side": "BUY"},
        ],
    )

    issue_ids = {issue.issue_id for issue in result.issues}
    assert "SUIT_DATA_QUALITY" in issue_ids
    assert "SUIT_LIQUIDITY_MAX" in issue_ids
    assert "SUIT_GOVERNANCE_BANNED" in issue_ids
    assert "SUIT_GOVERNANCE_SUSPENDED" in issue_ids
    assert "SUIT_GOVERNANCE_RESTRICTED_INCREASE" in issue_ids


def test_suitability_sets_highest_new_severity_to_low_when_only_low_issues_exist():
    before = _state(instrument_weights={}, cash_weight="1.0")
    after = _state(instrument_weights={"EQ_MISSING_ONLY": "0.01"}, cash_weight="0.99")
    options = EngineOptions(
        suitability_thresholds={
            "single_position_max_weight": "1.00",
            "issuer_max_weight": "1.00",
            "max_weight_by_liquidity_tier": {},
            "cash_band_min_weight": "0",
            "cash_band_max_weight": "1",
            "data_quality_issue_severity": "LOW",
        }
    )

    result = compute_suitability_result(
        before=before,
        after=after,
        shelf=[],
        options=options,
        portfolio_snapshot_id="pf_3",
        market_data_snapshot_id="md_3",
    )

    assert result.summary.new_count >= 1
    assert result.summary.highest_severity_new == "LOW"

