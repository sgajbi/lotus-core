from decimal import Decimal

from src.services.query_service.app.advisory_simulation.common.workflow_gates import (
    evaluate_gate_decision,
)
from src.services.query_service.app.advisory_simulation.models import (
    DiagnosticsData,
    EngineOptions,
    GateDecision,
    RuleResult,
    SuitabilityEvidence,
    SuitabilityEvidenceSnapshotIds,
    SuitabilityIssue,
    SuitabilityResult,
    SuitabilitySummary,
)


def _decision(
    *,
    status: str = "READY",
    rule_results: list[RuleResult] | None = None,
    suitability: SuitabilityResult | None = None,
    diagnostics: DiagnosticsData | None = None,
    options: EngineOptions | None = None,
    default_requires_client_consent: bool = False,
) -> GateDecision:
    return evaluate_gate_decision(
        status=status,
        rule_results=rule_results or [],
        suitability=suitability,
        diagnostics=diagnostics,
        options=options or EngineOptions(),
        default_requires_client_consent=default_requires_client_consent,
    )


def _suitability_issue(*, issue_id: str, issue_key: str, severity: str) -> SuitabilityIssue:
    return SuitabilityIssue(
        issue_id=issue_id,
        issue_key=issue_key,
        dimension="CONCENTRATION" if severity == "HIGH" else "LIQUIDITY",
        severity=severity,
        status_change="NEW",
        summary=f"{issue_key} issue",
        details={"threshold": "0.20", "measured_after": "0.40"},
        evidence=SuitabilityEvidence(
            as_of="md_2026_02_19",
            snapshot_ids=SuitabilityEvidenceSnapshotIds(
                portfolio_snapshot_id="pf_1",
                market_data_snapshot_id="md_1",
            ),
        ),
    )


def test_gate_decision_blocks_on_hard_fail() -> None:
    decision = _decision(
        rule_results=[
            RuleResult(
                rule_id="NO_SHORTING",
                severity="HARD",
                status="FAIL",
                measured=Decimal("-1"),
                threshold={"min": Decimal("0")},
                reason_code="SELL_EXCEEDS_HOLDINGS",
            )
        ]
    )

    assert decision.gate == "BLOCKED"
    assert decision.recommended_next_step == "FIX_INPUT"
    assert decision.summary.hard_fail_count == 1


def test_gate_decision_escalates_new_high_suitability_issue_to_compliance() -> None:
    suitability = SuitabilityResult(
        summary=SuitabilitySummary(
            new_count=1,
            resolved_count=0,
            persistent_count=0,
            highest_severity_new="HIGH",
        ),
        issues=[_suitability_issue(issue_id="SUIT_1", issue_key="issuer:ABC", severity="HIGH")],
        recommended_gate="COMPLIANCE_REVIEW",
    )

    decision = _decision(suitability=suitability)

    assert decision.gate == "COMPLIANCE_REVIEW_REQUIRED"
    assert decision.summary.new_high_suitability_count == 1


def test_gate_decision_escalates_soft_fail_and_new_medium_issue_to_risk() -> None:
    suitability = SuitabilityResult(
        summary=SuitabilitySummary(
            new_count=1,
            resolved_count=0,
            persistent_count=0,
            highest_severity_new="MEDIUM",
        ),
        issues=[_suitability_issue(issue_id="SUIT_2", issue_key="liq:L4", severity="MEDIUM")],
        recommended_gate="RISK_REVIEW",
    )

    decision = _decision(
        rule_results=[
            RuleResult(
                rule_id="CASH_BAND",
                severity="SOFT",
                status="FAIL",
                measured=Decimal("0.20"),
                threshold={"max": Decimal("0.10")},
                reason_code="THRESHOLD_BREACH",
            )
        ],
        suitability=suitability,
    )

    assert decision.gate == "RISK_REVIEW_REQUIRED"
    assert decision.summary.soft_fail_count == 1
    assert decision.summary.new_medium_suitability_count == 1


def test_gate_decision_respects_client_consent_requirements() -> None:
    decision = _decision(
        options=EngineOptions(workflow_requires_client_consent=True),
        default_requires_client_consent=False,
    )
    assert decision.gate == "CLIENT_CONSENT_REQUIRED"
    assert decision.recommended_next_step == "REQUEST_CLIENT_CONSENT"

    ready_to_execute = _decision(
        options=EngineOptions(client_consent_already_obtained=True),
    )
    assert ready_to_execute.gate == "EXECUTION_READY"


def test_gate_decision_includes_sorted_data_quality_reasons() -> None:
    decision = _decision(
        diagnostics=DiagnosticsData(
            data_quality={"price_missing": ["EQ_1"], "fx_missing": ["EUR/USD"], "shelf_missing": []}
        ),
    )

    assert [reason.reason_code for reason in decision.reasons] == [
        "DATA_QUALITY_MISSING_FX",
        "DATA_QUALITY_MISSING_PRICE",
    ]
