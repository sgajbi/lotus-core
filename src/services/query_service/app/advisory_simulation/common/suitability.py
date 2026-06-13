from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional

from src.services.query_service.app.advisory_simulation.models import (
    EngineOptions,
    ShelfEntry,
    SimulatedState,
    SuitabilityEvidence,
    SuitabilityEvidenceSnapshotIds,
    SuitabilityIssue,
    SuitabilityResult,
    SuitabilitySummary,
)

_STATUS_SORT = {"NEW": 0, "PERSISTENT": 1, "RESOLVED": 2}
_SEVERITY_SORT = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
_HIGH = "HIGH"
_MEDIUM = "MEDIUM"
_LOW = "LOW"
_EPSILON = Decimal("0.0000001")
_PRESENCE_GOVERNANCE_ISSUE_IDS = {
    "BANNED": "SUIT_GOVERNANCE_BANNED",
    "SUSPENDED": "SUIT_GOVERNANCE_SUSPENDED",
}


@dataclass(frozen=True)
class _IssueCandidate:
    issue_key: str
    issue_id: str
    dimension: str
    severity: str
    summary: str
    details: Dict[str, str]


def _to_instrument_weight_map(state: SimulatedState) -> Dict[str, Decimal]:
    return {
        metric.key: metric.weight for metric in state.allocation_by_instrument if metric.weight > 0
    }


def _to_cash_weight(state: SimulatedState) -> Decimal:
    return next(
        (metric.weight for metric in state.allocation_by_asset_class if metric.key == "CASH"),
        Decimal("0"),
    )


def _severity_for_concentration(measured: Decimal, limit: Decimal) -> str:
    if measured > (limit * Decimal("1.25")):
        return _HIGH
    return _MEDIUM


def _issue_data_quality(
    *,
    issue_key: str,
    summary: str,
    details: Dict[str, str],
    severity: str,
) -> _IssueCandidate:
    return _IssueCandidate(
        issue_key=issue_key,
        issue_id="SUIT_DATA_QUALITY",
        dimension="DATA_QUALITY",
        severity=severity,
        summary=summary,
        details=details,
    )


def _append_single_position_issues(
    *,
    issue_map: Dict[str, _IssueCandidate],
    target_weights: Dict[str, Decimal],
    thresholds: Any,
) -> None:
    for instrument_id, weight in target_weights.items():
        if weight <= thresholds.single_position_max_weight + _EPSILON:
            continue
        issue_key = f"SINGLE_POSITION_MAX|{instrument_id}"
        issue_map[issue_key] = _IssueCandidate(
            issue_key=issue_key,
            issue_id="SUIT_SINGLE_POSITION_MAX",
            dimension="CONCENTRATION",
            severity=_severity_for_concentration(weight, thresholds.single_position_max_weight),
            summary=(
                f"Single position {instrument_id} exceeds "
                f"{thresholds.single_position_max_weight:.2%} cap."
            ),
            details={
                "instrument_id": instrument_id,
                "threshold": str(thresholds.single_position_max_weight),
                "measured": str(weight),
            },
        )


def _issuer_weights_for_target(
    *,
    issue_map: Dict[str, _IssueCandidate],
    target_weights: Dict[str, Decimal],
    shelf_by_instrument: Dict[str, ShelfEntry],
    thresholds: Any,
) -> Dict[str, Decimal]:
    issuer_weights: Dict[str, Decimal] = {}
    for instrument_id, weight in target_weights.items():
        shelf_entry = shelf_by_instrument.get(instrument_id)
        if shelf_entry is None:
            dq_key = f"DQ|MISSING_SHELF|{instrument_id}"
            issue_map[dq_key] = _issue_data_quality(
                issue_key=dq_key,
                summary=f"Shelf enrichment missing for {instrument_id}.",
                details={
                    "instrument_id": instrument_id,
                    "missing_fields": "shelf_entry",
                },
                severity=thresholds.data_quality_issue_severity,
            )
            continue

        if not shelf_entry.issuer_id:
            dq_key = f"DQ|MISSING_ISSUER|{instrument_id}"
            issue_map[dq_key] = _issue_data_quality(
                issue_key=dq_key,
                summary=f"Issuer enrichment missing for {instrument_id}.",
                details={
                    "instrument_id": instrument_id,
                    "missing_fields": "issuer_id",
                },
                severity=thresholds.data_quality_issue_severity,
            )
            continue

        issuer_weights[shelf_entry.issuer_id] = (
            issuer_weights.get(
                shelf_entry.issuer_id,
                Decimal("0"),
            )
            + weight
        )
    return issuer_weights


def _append_issuer_concentration_issues(
    *,
    issue_map: Dict[str, _IssueCandidate],
    issuer_weights: Dict[str, Decimal],
    thresholds: Any,
) -> None:
    for issuer_id, weight in issuer_weights.items():
        if weight <= thresholds.issuer_max_weight + _EPSILON:
            continue
        issue_key = f"ISSUER_MAX|{issuer_id}"
        issue_map[issue_key] = _IssueCandidate(
            issue_key=issue_key,
            issue_id="SUIT_ISSUER_MAX",
            dimension="ISSUER",
            severity=_severity_for_concentration(weight, thresholds.issuer_max_weight),
            summary=f"Issuer {issuer_id} exceeds {thresholds.issuer_max_weight:.2%} exposure cap.",
            details={
                "issuer_id": issuer_id,
                "threshold": str(thresholds.issuer_max_weight),
                "measured": str(weight),
            },
        )


def _liquidity_weights_for_target(
    *,
    issue_map: Dict[str, _IssueCandidate],
    target_weights: Dict[str, Decimal],
    shelf_by_instrument: Dict[str, ShelfEntry],
    thresholds: Any,
) -> Dict[str, Decimal]:
    liquidity_weights: Dict[str, Decimal] = {}
    for instrument_id, weight in target_weights.items():
        shelf_entry = shelf_by_instrument.get(instrument_id)
        if shelf_entry is None:
            continue
        if not shelf_entry.liquidity_tier:
            dq_key = f"DQ|MISSING_LIQUIDITY_TIER|{instrument_id}"
            issue_map[dq_key] = _issue_data_quality(
                issue_key=dq_key,
                summary=f"Liquidity tier enrichment missing for {instrument_id}.",
                details={
                    "instrument_id": instrument_id,
                    "missing_fields": "liquidity_tier",
                },
                severity=thresholds.data_quality_issue_severity,
            )
            continue
        liquidity_weights[shelf_entry.liquidity_tier] = (
            liquidity_weights.get(
                shelf_entry.liquidity_tier,
                Decimal("0"),
            )
            + weight
        )
    return liquidity_weights


def _append_liquidity_concentration_issues(
    *,
    issue_map: Dict[str, _IssueCandidate],
    liquidity_weights: Dict[str, Decimal],
    thresholds: Any,
) -> None:
    for tier, cap in thresholds.max_weight_by_liquidity_tier.items():
        measured = liquidity_weights.get(tier, Decimal("0"))
        if measured <= cap + _EPSILON:
            continue
        issue_key = f"LIQUIDITY_MAX|{tier}"
        issue_map[issue_key] = _IssueCandidate(
            issue_key=issue_key,
            issue_id="SUIT_LIQUIDITY_MAX",
            dimension="LIQUIDITY",
            severity=_severity_for_concentration(measured, cap),
            summary=f"Liquidity tier {tier} exceeds {cap:.2%} exposure cap.",
            details={
                "liquidity_tier": tier,
                "threshold": str(cap),
                "measured": str(measured),
            },
        )


def _governance_issue_for_instrument(
    *,
    instrument_id: str,
    shelf_entry: ShelfEntry,
    before_weight: Decimal,
    after_weight: Decimal,
    options: EngineOptions,
) -> Optional[_IssueCandidate]:
    status = shelf_entry.status
    return _first_issue(
        _governance_presence_issue(
            instrument_id=instrument_id,
            status=status,
            after_weight=after_weight,
        ),
        _sell_only_increase_issue(
            instrument_id=instrument_id,
            status=status,
            before_weight=before_weight,
            after_weight=after_weight,
        ),
        _restricted_increase_issue(
            instrument_id=instrument_id,
            status=status,
            before_weight=before_weight,
            after_weight=after_weight,
            allow_restricted=options.allow_restricted,
        ),
    )


def _first_issue(*issues: Optional[_IssueCandidate]) -> Optional[_IssueCandidate]:
    return next((issue for issue in issues if issue is not None), None)


def _governance_issue_key(instrument_id: str, status: str) -> str:
    return f"GOVERNANCE|{instrument_id}|{status}"


def _governance_presence_issue(
    *,
    instrument_id: str,
    status: str,
    after_weight: Decimal,
) -> Optional[_IssueCandidate]:
    issue_id = _PRESENCE_GOVERNANCE_ISSUE_IDS.get(status)
    if issue_id is None or after_weight <= _EPSILON:
        return None
    return _IssueCandidate(
        issue_key=_governance_issue_key(instrument_id, status),
        issue_id=issue_id,
        dimension="GOVERNANCE",
        severity=_HIGH,
        summary=f"{status} instrument {instrument_id} is present in the portfolio.",
        details={
            "instrument_id": instrument_id,
            "shelf_status": status,
            "measured": str(after_weight),
        },
    )


def _sell_only_increase_issue(
    *,
    instrument_id: str,
    status: str,
    before_weight: Decimal,
    after_weight: Decimal,
) -> Optional[_IssueCandidate]:
    if status != "SELL_ONLY" or after_weight <= before_weight + _EPSILON:
        return None
    return _IssueCandidate(
        issue_key=_governance_issue_key(instrument_id, status),
        issue_id="SUIT_GOVERNANCE_SELL_ONLY_INCREASE",
        dimension="GOVERNANCE",
        severity=_HIGH,
        summary=f"SELL_ONLY instrument {instrument_id} increased in proposed state.",
        details={
            "instrument_id": instrument_id,
            "shelf_status": status,
            "measured_before": str(before_weight),
            "measured_after": str(after_weight),
        },
    )


def _restricted_increase_issue(
    *,
    instrument_id: str,
    status: str,
    before_weight: Decimal,
    after_weight: Decimal,
    allow_restricted: bool,
) -> Optional[_IssueCandidate]:
    if status != "RESTRICTED" or after_weight <= before_weight + _EPSILON:
        return None
    allowed_severity = _MEDIUM if allow_restricted else _HIGH
    return _IssueCandidate(
        issue_key=_governance_issue_key(instrument_id, status),
        issue_id="SUIT_GOVERNANCE_RESTRICTED_INCREASE",
        dimension="GOVERNANCE",
        severity=allowed_severity,
        summary=(
            f"RESTRICTED instrument {instrument_id} increased in proposed state"
            if not allow_restricted
            else f"RESTRICTED instrument {instrument_id} increased under allow_restricted"
        ),
        details={
            "instrument_id": instrument_id,
            "shelf_status": status,
            "allow_restricted": str(allow_restricted).lower(),
            "measured_before": str(before_weight),
            "measured_after": str(after_weight),
        },
    )


def _governance_trade_attempt_issue(
    *,
    instrument_id: str,
    shelf_entry: ShelfEntry,
    before_weights: Dict[str, Decimal],
    after_weights: Dict[str, Decimal],
    options: EngineOptions,
) -> Optional[_IssueCandidate]:
    if shelf_entry.status == "SELL_ONLY":
        return _IssueCandidate(
            issue_key=_governance_issue_key(instrument_id, shelf_entry.status),
            issue_id="SUIT_GOVERNANCE_SELL_ONLY_INCREASE",
            dimension="GOVERNANCE",
            severity=_HIGH,
            summary=f"Proposal BUY attempts to increase SELL_ONLY instrument {instrument_id}.",
            details={
                "instrument_id": instrument_id,
                "shelf_status": shelf_entry.status,
                "measured_before": str(before_weights.get(instrument_id, Decimal("0"))),
                "measured_after": str(after_weights.get(instrument_id, Decimal("0"))),
            },
        )

    if shelf_entry.status == "RESTRICTED":
        allowed_severity = _MEDIUM if options.allow_restricted else _HIGH
        return _IssueCandidate(
            issue_key=_governance_issue_key(instrument_id, shelf_entry.status),
            issue_id="SUIT_GOVERNANCE_RESTRICTED_INCREASE",
            dimension="GOVERNANCE",
            severity=allowed_severity,
            summary=f"Proposal BUY attempts to increase RESTRICTED instrument {instrument_id}.",
            details={
                "instrument_id": instrument_id,
                "shelf_status": shelf_entry.status,
                "allow_restricted": str(options.allow_restricted).lower(),
                "measured_before": str(before_weights.get(instrument_id, Decimal("0"))),
                "measured_after": str(after_weights.get(instrument_id, Decimal("0"))),
            },
        )

    return None


def _append_governance_state_issues(
    *,
    issue_map: Dict[str, _IssueCandidate],
    before_weights: Dict[str, Decimal],
    target_weights: Dict[str, Decimal],
    shelf_by_instrument: Dict[str, ShelfEntry],
    options: EngineOptions,
) -> None:
    all_instruments = set(before_weights.keys()) | set(target_weights.keys())
    for instrument_id in sorted(all_instruments):
        shelf_entry = shelf_by_instrument.get(instrument_id)
        if shelf_entry is None:
            continue
        issue = _governance_issue_for_instrument(
            instrument_id=instrument_id,
            shelf_entry=shelf_entry,
            before_weight=before_weights.get(instrument_id, Decimal("0")),
            after_weight=target_weights.get(instrument_id, Decimal("0")),
            options=options,
        )
        if issue is not None:
            issue_map[issue.issue_key] = issue


def _append_cash_band_issue(
    *,
    issue_map: Dict[str, _IssueCandidate],
    target_state: SimulatedState,
    thresholds: Any,
) -> None:
    cash_weight = _to_cash_weight(target_state)
    if (
        cash_weight >= thresholds.cash_band_min_weight - _EPSILON
        and cash_weight <= thresholds.cash_band_max_weight + _EPSILON
    ):
        return
    issue_map["CASH_BAND"] = _IssueCandidate(
        issue_key="CASH_BAND",
        issue_id="SUIT_CASH_BAND",
        dimension="CASH",
        severity=_MEDIUM,
        summary="Cash weight is outside advisory suitability band.",
        details={
            "threshold_min": str(thresholds.cash_band_min_weight),
            "threshold_max": str(thresholds.cash_band_max_weight),
            "measured": str(cash_weight),
        },
    )


def _scan_state_issues(
    *,
    target_state: SimulatedState,
    before_state: SimulatedState,
    shelf_by_instrument: Dict[str, ShelfEntry],
    options: EngineOptions,
) -> Dict[str, _IssueCandidate]:
    thresholds = options.suitability_thresholds
    issue_map: Dict[str, _IssueCandidate] = {}

    target_weights = _to_instrument_weight_map(target_state)
    before_weights = _to_instrument_weight_map(before_state)

    _append_single_position_issues(
        issue_map=issue_map,
        target_weights=target_weights,
        thresholds=thresholds,
    )
    issuer_weights = _issuer_weights_for_target(
        issue_map=issue_map,
        target_weights=target_weights,
        shelf_by_instrument=shelf_by_instrument,
        thresholds=thresholds,
    )
    _append_issuer_concentration_issues(
        issue_map=issue_map,
        issuer_weights=issuer_weights,
        thresholds=thresholds,
    )
    liquidity_weights = _liquidity_weights_for_target(
        issue_map=issue_map,
        target_weights=target_weights,
        shelf_by_instrument=shelf_by_instrument,
        thresholds=thresholds,
    )
    _append_liquidity_concentration_issues(
        issue_map=issue_map,
        liquidity_weights=liquidity_weights,
        thresholds=thresholds,
    )
    _append_governance_state_issues(
        issue_map=issue_map,
        before_weights=before_weights,
        target_weights=target_weights,
        shelf_by_instrument=shelf_by_instrument,
        options=options,
    )
    _append_cash_band_issue(
        issue_map=issue_map,
        target_state=target_state,
        thresholds=thresholds,
    )

    return issue_map


def _trade_field(trade: Any, field: str) -> Any:
    if isinstance(trade, dict):
        return trade.get(field)
    return getattr(trade, field, None)


def _append_governance_trade_attempt_issues(
    *,
    after_issues: Dict[str, _IssueCandidate],
    before: SimulatedState,
    after: SimulatedState,
    shelf_by_instrument: Dict[str, ShelfEntry],
    proposed_trades: list[Any],
    options: EngineOptions,
) -> None:
    before_weights = _to_instrument_weight_map(before)
    after_weights = _to_instrument_weight_map(after)

    for trade in proposed_trades:
        if _trade_field(trade, "side") != "BUY":
            continue
        instrument_id = _trade_field(trade, "instrument_id")
        if not instrument_id:
            continue
        shelf_entry = shelf_by_instrument.get(instrument_id)
        if shelf_entry is None:
            continue
        issue = _governance_trade_attempt_issue(
            instrument_id=instrument_id,
            shelf_entry=shelf_entry,
            before_weights=before_weights,
            after_weights=after_weights,
            options=options,
        )
        if issue is not None:
            after_issues[issue.issue_key] = issue


def _build_suitability_issue(
    *,
    status_change: str,
    candidate: _IssueCandidate,
    evidence: SuitabilityEvidence,
) -> SuitabilityIssue:
    return SuitabilityIssue(
        issue_id=candidate.issue_id,
        issue_key=candidate.issue_key,
        dimension=candidate.dimension,
        severity=candidate.severity,
        status_change=status_change,
        summary=candidate.summary,
        details=candidate.details,
        evidence=evidence,
    )


def _status_change_for_issue(
    *,
    issue_key: str,
    before_issues: Dict[str, _IssueCandidate],
    after_issues: Dict[str, _IssueCandidate],
) -> Optional[str]:
    in_before = issue_key in before_issues
    in_after = issue_key in after_issues
    if in_after and not in_before:
        return "NEW"
    if in_before and in_after:
        return "PERSISTENT"
    if in_before:
        return "RESOLVED"
    return None


def _candidate_for_status(
    *,
    issue_key: str,
    status_change: str,
    before_issues: Dict[str, _IssueCandidate],
    after_issues: Dict[str, _IssueCandidate],
) -> _IssueCandidate:
    if status_change == "RESOLVED":
        return before_issues[issue_key]
    return after_issues[issue_key]


def _classify_issues(
    *,
    before_issues: Dict[str, _IssueCandidate],
    after_issues: Dict[str, _IssueCandidate],
    evidence: SuitabilityEvidence,
) -> list[SuitabilityIssue]:
    issue_keys = set(before_issues.keys()) | set(after_issues.keys())
    issues: list[SuitabilityIssue] = []

    for issue_key in issue_keys:
        status_change = _status_change_for_issue(
            issue_key=issue_key,
            before_issues=before_issues,
            after_issues=after_issues,
        )
        if status_change is None:
            continue
        issues.append(
            _build_suitability_issue(
                status_change=status_change,
                candidate=_candidate_for_status(
                    issue_key=issue_key,
                    status_change=status_change,
                    before_issues=before_issues,
                    after_issues=after_issues,
                ),
                evidence=evidence,
            )
        )

    issues.sort(
        key=lambda issue: (
            _STATUS_SORT[issue.status_change],
            _SEVERITY_SORT[issue.severity],
            issue.dimension,
            issue.issue_key,
        )
    )

    return issues


def _new_issues(issues: Iterable[SuitabilityIssue]) -> list[SuitabilityIssue]:
    return [issue for issue in issues if issue.status_change == "NEW"]


def _recommended_gate(issues: Iterable[SuitabilityIssue]) -> str:
    new_issue_list = _new_issues(issues)
    if any(issue.severity == _HIGH for issue in new_issue_list):
        return "COMPLIANCE_REVIEW"
    if any(issue.severity == _MEDIUM for issue in new_issue_list):
        return "RISK_REVIEW"
    return "NONE"


def _suitability_evidence(
    *,
    evidence_as_of: Optional[str],
    portfolio_snapshot_id: str,
    market_data_snapshot_id: str,
) -> SuitabilityEvidence:
    return SuitabilityEvidence(
        as_of=evidence_as_of or market_data_snapshot_id,
        snapshot_ids=SuitabilityEvidenceSnapshotIds(
            portfolio_snapshot_id=portfolio_snapshot_id,
            market_data_snapshot_id=market_data_snapshot_id,
        ),
    )


def _issues_with_status(
    issues: Iterable[SuitabilityIssue],
    status_change: str,
) -> list[SuitabilityIssue]:
    return [issue for issue in issues if issue.status_change == status_change]


def _highest_new_severity(new_issues: Iterable[SuitabilityIssue]) -> Optional[str]:
    severities = {issue.severity for issue in new_issues}
    for severity in (_HIGH, _MEDIUM, _LOW):
        if severity in severities:
            return severity
    return None


def _suitability_summary(issues: list[SuitabilityIssue]) -> SuitabilitySummary:
    new_issues = _issues_with_status(issues, "NEW")
    return SuitabilitySummary(
        new_count=len(new_issues),
        resolved_count=len(_issues_with_status(issues, "RESOLVED")),
        persistent_count=len(_issues_with_status(issues, "PERSISTENT")),
        highest_severity_new=_highest_new_severity(new_issues),
    )


def compute_suitability_result(
    *,
    before: SimulatedState,
    after: SimulatedState,
    shelf: list[ShelfEntry],
    options: EngineOptions,
    portfolio_snapshot_id: str,
    market_data_snapshot_id: str,
    evidence_as_of: Optional[str] = None,
    proposed_trades: Optional[list[Any]] = None,
) -> SuitabilityResult:
    shelf_by_instrument = {entry.instrument_id: entry for entry in shelf}
    before_issues = _scan_state_issues(
        target_state=before,
        before_state=before,
        shelf_by_instrument=shelf_by_instrument,
        options=options,
    )
    after_issues = _scan_state_issues(
        target_state=after,
        before_state=before,
        shelf_by_instrument=shelf_by_instrument,
        options=options,
    )
    _append_governance_trade_attempt_issues(
        after_issues=after_issues,
        before=before,
        after=after,
        shelf_by_instrument=shelf_by_instrument,
        proposed_trades=proposed_trades or [],
        options=options,
    )

    evidence = _suitability_evidence(
        evidence_as_of=evidence_as_of,
        portfolio_snapshot_id=portfolio_snapshot_id,
        market_data_snapshot_id=market_data_snapshot_id,
    )
    issues = _classify_issues(
        before_issues=before_issues,
        after_issues=after_issues,
        evidence=evidence,
    )

    return SuitabilityResult(
        summary=_suitability_summary(issues),
        issues=issues,
        recommended_gate=_recommended_gate(issues),
    )
