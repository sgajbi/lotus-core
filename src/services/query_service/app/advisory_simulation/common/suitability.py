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

    for instrument_id, weight in target_weights.items():
        if weight > thresholds.single_position_max_weight + _EPSILON:
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
        else:
            issuer_weights[shelf_entry.issuer_id] = (
                issuer_weights.get(
                    shelf_entry.issuer_id,
                    Decimal("0"),
                )
                + weight
            )

    for issuer_id, weight in issuer_weights.items():
        if weight > thresholds.issuer_max_weight + _EPSILON:
            issue_key = f"ISSUER_MAX|{issuer_id}"
            issue_map[issue_key] = _IssueCandidate(
                issue_key=issue_key,
                issue_id="SUIT_ISSUER_MAX",
                dimension="ISSUER",
                severity=_severity_for_concentration(weight, thresholds.issuer_max_weight),
                summary=(
                    f"Issuer {issuer_id} exceeds {thresholds.issuer_max_weight:.2%} exposure cap."
                ),
                details={
                    "issuer_id": issuer_id,
                    "threshold": str(thresholds.issuer_max_weight),
                    "measured": str(weight),
                },
            )

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

    for tier, cap in thresholds.max_weight_by_liquidity_tier.items():
        measured = liquidity_weights.get(tier, Decimal("0"))
        if measured > cap + _EPSILON:
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

    all_instruments = set(before_weights.keys()) | set(target_weights.keys())
    for instrument_id in sorted(all_instruments):
        shelf_entry = shelf_by_instrument.get(instrument_id)
        if shelf_entry is None:
            continue
        before_weight = before_weights.get(instrument_id, Decimal("0"))
        after_weight = target_weights.get(instrument_id, Decimal("0"))
        status = shelf_entry.status
        issue_key = f"GOVERNANCE|{instrument_id}|{status}"

        if status == "BANNED" and after_weight > _EPSILON:
            issue_map[issue_key] = _IssueCandidate(
                issue_key=issue_key,
                issue_id="SUIT_GOVERNANCE_BANNED",
                dimension="GOVERNANCE",
                severity=_HIGH,
                summary=f"BANNED instrument {instrument_id} is present in the portfolio.",
                details={
                    "instrument_id": instrument_id,
                    "shelf_status": status,
                    "measured": str(after_weight),
                },
            )

        if status == "SUSPENDED" and after_weight > _EPSILON:
            issue_map[issue_key] = _IssueCandidate(
                issue_key=issue_key,
                issue_id="SUIT_GOVERNANCE_SUSPENDED",
                dimension="GOVERNANCE",
                severity=_HIGH,
                summary=f"SUSPENDED instrument {instrument_id} is present in the portfolio.",
                details={
                    "instrument_id": instrument_id,
                    "shelf_status": status,
                    "measured": str(after_weight),
                },
            )

        if status == "SELL_ONLY" and after_weight > before_weight + _EPSILON:
            issue_map[issue_key] = _IssueCandidate(
                issue_key=issue_key,
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

        if status == "RESTRICTED" and after_weight > before_weight + _EPSILON:
            allowed_severity = _MEDIUM if options.allow_restricted else _HIGH
            issue_map[issue_key] = _IssueCandidate(
                issue_key=issue_key,
                issue_id="SUIT_GOVERNANCE_RESTRICTED_INCREASE",
                dimension="GOVERNANCE",
                severity=allowed_severity,
                summary=(
                    f"RESTRICTED instrument {instrument_id} increased in proposed state"
                    if not options.allow_restricted
                    else f"RESTRICTED instrument {instrument_id} increased under allow_restricted"
                ),
                details={
                    "instrument_id": instrument_id,
                    "shelf_status": status,
                    "allow_restricted": str(options.allow_restricted).lower(),
                    "measured_before": str(before_weight),
                    "measured_after": str(after_weight),
                },
            )

    cash_weight = _to_cash_weight(target_state)
    if (
        cash_weight < thresholds.cash_band_min_weight - _EPSILON
        or cash_weight > thresholds.cash_band_max_weight + _EPSILON
    ):
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
        issue_key = f"GOVERNANCE|{instrument_id}|{shelf_entry.status}"
        if shelf_entry.status == "SELL_ONLY":
            after_issues[issue_key] = _IssueCandidate(
                issue_key=issue_key,
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
            after_issues[issue_key] = _IssueCandidate(
                issue_key=issue_key,
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


def _classify_issues(
    *,
    before_issues: Dict[str, _IssueCandidate],
    after_issues: Dict[str, _IssueCandidate],
    evidence: SuitabilityEvidence,
) -> list[SuitabilityIssue]:
    issue_keys = set(before_issues.keys()) | set(after_issues.keys())
    issues: list[SuitabilityIssue] = []

    for issue_key in issue_keys:
        in_before = issue_key in before_issues
        in_after = issue_key in after_issues

        if in_after and not in_before:
            issues.append(
                _build_suitability_issue(
                    status_change="NEW",
                    candidate=after_issues[issue_key],
                    evidence=evidence,
                )
            )
        elif in_before and in_after:
            issues.append(
                _build_suitability_issue(
                    status_change="PERSISTENT",
                    candidate=after_issues[issue_key],
                    evidence=evidence,
                )
            )
        elif in_before:
            issues.append(
                _build_suitability_issue(
                    status_change="RESOLVED",
                    candidate=before_issues[issue_key],
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


def _recommended_gate(issues: Iterable[SuitabilityIssue]) -> str:
    new_issues = [issue for issue in issues if issue.status_change == "NEW"]
    if any(issue.severity == _HIGH for issue in new_issues):
        return "COMPLIANCE_REVIEW"
    if any(issue.severity == _MEDIUM for issue in new_issues):
        return "RISK_REVIEW"
    return "NONE"


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

    evidence = SuitabilityEvidence(
        as_of=evidence_as_of or market_data_snapshot_id,
        snapshot_ids=SuitabilityEvidenceSnapshotIds(
            portfolio_snapshot_id=portfolio_snapshot_id,
            market_data_snapshot_id=market_data_snapshot_id,
        ),
    )

    issues = _classify_issues(
        before_issues=before_issues,
        after_issues=after_issues,
        evidence=evidence,
    )

    new_issues = [issue for issue in issues if issue.status_change == "NEW"]
    resolved_issues = [issue for issue in issues if issue.status_change == "RESOLVED"]
    persistent_issues = [issue for issue in issues if issue.status_change == "PERSISTENT"]
    highest_severity_new = None
    if any(issue.severity == _HIGH for issue in new_issues):
        highest_severity_new = _HIGH
    elif any(issue.severity == _MEDIUM for issue in new_issues):
        highest_severity_new = _MEDIUM
    elif any(issue.severity == _LOW for issue in new_issues):
        highest_severity_new = _LOW

    return SuitabilityResult(
        summary=SuitabilitySummary(
            new_count=len(new_issues),
            resolved_count=len(resolved_issues),
            persistent_count=len(persistent_issues),
            highest_severity_new=highest_severity_new,
        ),
        issues=issues,
        recommended_gate=_recommended_gate(issues),
    )
