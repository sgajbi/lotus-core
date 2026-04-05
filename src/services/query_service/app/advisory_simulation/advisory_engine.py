from copy import deepcopy
from decimal import Decimal
from typing import Any, Optional

from src.services.query_service.app.advisory_simulation.advisory.funding import (
    build_auto_funding_plan,
)
from src.services.query_service.app.advisory_simulation.advisory.ids import (
    proposal_run_id_from_request_hash,
)
from src.services.query_service.app.advisory_simulation.advisory.intents import (
    apply_proposal_cash_flow,
    build_proposal_security_trade_intent,
    expected_cash_delta_base,
)
from src.services.query_service.app.advisory_simulation.common.diagnostics import (
    make_diagnostics_data,
)
from src.services.query_service.app.advisory_simulation.common.drift_analytics import (
    compute_drift_analysis,
)
from src.services.query_service.app.advisory_simulation.common.intent_dependencies import (
    link_buy_intent_dependencies,
)
from src.services.query_service.app.advisory_simulation.common.simulation_shared import (
    apply_security_trade_to_portfolio,
    build_reconciliation,
    derive_status_from_rules,
    sort_execution_intents,
)
from src.services.query_service.app.advisory_simulation.common.suitability import (
    compute_suitability_result,
)
from src.services.query_service.app.advisory_simulation.common.workflow_gates import (
    evaluate_gate_decision,
)
from src.services.query_service.app.advisory_simulation.compliance import RuleEngine
from src.services.query_service.app.advisory_simulation.models import (
    CashFlowIntent,
    EngineOptions,
    LineageData,
    MarketDataSnapshot,
    PortfolioSnapshot,
    ProposalResult,
    ProposedCashFlow,
    ProposedTrade,
    ReferenceModel,
    RuleResult,
    ShelfEntry,
    ValuationMode,
)
from src.services.query_service.app.advisory_simulation.valuation import build_simulated_state


def run_proposal_simulation(
    *,
    portfolio: PortfolioSnapshot,
    market_data: MarketDataSnapshot,
    shelf: list[ShelfEntry],
    options: EngineOptions,
    proposed_cash_flows: list[ProposedCashFlow] | list[dict[str, Any]],
    proposed_trades: list[ProposedTrade] | list[dict[str, Any]],
    reference_model: Optional[ReferenceModel | dict[str, Any]] = None,
    request_hash: str = "no_hash",
    idempotency_key: Optional[str] = None,
    correlation_id: str = "c_none",
    simulation_contract_version: Optional[str] = None,
) -> ProposalResult:
    run_id = proposal_run_id_from_request_hash(request_hash)
    diagnostics = make_diagnostics_data()

    before = build_simulated_state(
        portfolio,
        market_data,
        shelf,
        diagnostics.data_quality,
        diagnostics.warnings,
        options,
    )
    after_portfolio = deepcopy(portfolio)

    hard_failures = []
    force_pending_review = False

    cash_flows = [ProposedCashFlow.model_validate(item) for item in proposed_cash_flows]
    trades = [ProposedTrade.model_validate(item) for item in proposed_trades]
    reference_model_validated = (
        ReferenceModel.model_validate(reference_model) if reference_model is not None else None
    )

    cash_flow_intents = []
    for idx, cash_flow in enumerate(cash_flows):
        apply_proposal_cash_flow(after_portfolio, cash_flow)
        cash_flow_intents.append(
            CashFlowIntent(
                intent_id=f"oi_cf_{idx + 1}",
                currency=cash_flow.currency,
                amount=cash_flow.amount,
                description=cash_flow.description,
            )
        )
        if options.proposal_block_negative_cash:
            cash_entry = next(
                (x for x in after_portfolio.cash_balances if x.currency == cash_flow.currency),
                None,
            )
            if cash_entry is not None and cash_entry.amount < Decimal("0"):
                diagnostics.warnings.append("PROPOSAL_WITHDRAWAL_NEGATIVE_CASH")
                hard_failures.append("PROPOSAL_WITHDRAWAL_NEGATIVE_CASH")

    shelf_by_instrument = {entry.instrument_id: entry for entry in shelf}
    security_intents = []
    for idx, trade in enumerate(trades):
        shelf_entry = shelf_by_instrument.get(trade.instrument_id)
        if shelf_entry is None:
            diagnostics.data_quality["shelf_missing"].append(trade.instrument_id)
            continue

        if trade.side == "BUY" and shelf_entry.status in {"SELL_ONLY", "BANNED", "SUSPENDED"}:
            diagnostics.warnings.append("PROPOSAL_TRADE_NOT_SUPPORTED_BY_SHELF")
            hard_failures.append("PROPOSAL_TRADE_NOT_SUPPORTED_BY_SHELF")
            continue
        if (
            trade.side == "BUY"
            and shelf_entry.status == "RESTRICTED"
            and not options.allow_restricted
        ):
            diagnostics.warnings.append("PROPOSAL_TRADE_NOT_SUPPORTED_BY_SHELF")
            hard_failures.append("PROPOSAL_TRADE_NOT_SUPPORTED_BY_SHELF")
            continue

        intent, error_code = build_proposal_security_trade_intent(
            trade=trade,
            market_data=market_data,
            base_currency=portfolio.base_currency,
            intent_id=f"oi_{idx + 1}",
            dq_log=diagnostics.data_quality,
        )
        if error_code:
            diagnostics.warnings.append(error_code)
            hard_failures.append(error_code)
        if intent is not None:
            security_intents.append(intent)

    sell_intents = sorted(
        [intent for intent in security_intents if intent.side == "SELL"],
        key=lambda intent: intent.instrument_id,
    )
    buy_intents = sorted(
        [intent for intent in security_intents if intent.side == "BUY"],
        key=lambda intent: intent.instrument_id,
    )

    for sell_intent in sell_intents:
        apply_security_trade_to_portfolio(after_portfolio, sell_intent)

    (
        fx_intents,
        fx_by_currency,
        unfunded_currencies,
        funding_failures,
        funding_pending,
    ) = build_auto_funding_plan(
        after_portfolio=after_portfolio,
        market_data=market_data,
        options=options,
        buy_intents=buy_intents,
        diagnostics=diagnostics,
    )
    hard_failures.extend(funding_failures)
    force_pending_review = force_pending_review or funding_pending

    executable_buy_intents = []
    for buy_intent in buy_intents:
        if buy_intent.notional is None:
            continue
        if buy_intent.notional.currency in unfunded_currencies:
            if "PROPOSAL_BUY_SKIPPED_UNFUNDED" not in diagnostics.warnings:
                diagnostics.warnings.append("PROPOSAL_BUY_SKIPPED_UNFUNDED")
            continue
        apply_security_trade_to_portfolio(after_portfolio, buy_intent)
        executable_buy_intents.append(buy_intent)

    include_sell_dependency = options.link_buy_to_same_currency_sell_dependency
    if include_sell_dependency is None:
        include_sell_dependency = False
    link_buy_intent_dependencies(
        sell_intents + executable_buy_intents,
        fx_intent_id_by_currency=fx_by_currency,
        include_same_currency_sell_dependency=include_sell_dependency,
    )

    fx_intents = sorted(fx_intents, key=lambda intent: intent.pair)
    intents = sort_execution_intents(
        cash_flow_intents + sell_intents + fx_intents + executable_buy_intents
    )

    after = build_simulated_state(
        after_portfolio,
        market_data,
        shelf,
        diagnostics.data_quality,
        diagnostics.warnings,
        options.model_copy(update={"valuation_mode": ValuationMode.CALCULATED}),
    )
    rule_results = RuleEngine.evaluate(after, options, diagnostics)

    if hard_failures:
        measured = Decimal(len(hard_failures))
        rule_results.append(
            RuleResult(
                rule_id="PROPOSAL_INPUT_GUARDS",
                severity="HARD",
                status="FAIL",
                measured=measured,
                threshold={"max": Decimal("0")},
                reason_code=hard_failures[0],
                remediation_hint=(
                    "Adjust proposal cash flows, funding inputs, or shelf eligibility."
                ),
            )
        )

    if force_pending_review:
        rule_results.append(
            RuleResult(
                rule_id="PROPOSAL_FUNDING_DQ",
                severity="SOFT",
                status="FAIL",
                measured=Decimal(len(diagnostics.missing_fx_pairs)),
                threshold={"max": Decimal("0")},
                reason_code="MISSING_FX_FOR_FUNDING",
                remediation_hint="Provide required FX rates for advisory auto-funding.",
            )
        )

    final_status = derive_status_from_rules(rule_results)

    expected_delta_base = expected_cash_delta_base(
        portfolio=portfolio,
        market_data=market_data,
        cash_flows=cash_flows,
        dq_log=diagnostics.data_quality,
    )
    expected_after_total = before.total_value.amount + expected_delta_base
    reconciliation, recon_diff, tolerance = build_reconciliation(
        before_total=before.total_value.amount,
        after_total=after.total_value.amount,
        expected_after_total=expected_after_total,
        base_currency=portfolio.base_currency,
        use_absolute_scale=True,
    )

    if reconciliation.status == "MISMATCH":
        final_status = "BLOCKED"
        rule_results.append(
            RuleResult(
                rule_id="RECONCILIATION",
                severity="HARD",
                status="FAIL",
                measured=recon_diff,
                threshold={"max": tolerance},
                reason_code="VALUE_MISMATCH",
                remediation_hint="Check pricing/FX or proposal inputs.",
            )
        )

    if force_pending_review and final_status == "READY":
        final_status = "PENDING_REVIEW"

    drift_analysis = None
    if options.enable_drift_analytics and reference_model_validated is not None:
        if reference_model_validated.base_currency != portfolio.base_currency:
            diagnostics.warnings.append("REFERENCE_MODEL_BASE_CURRENCY_MISMATCH")
        else:
            traded_instruments = {
                intent.instrument_id for intent in intents if intent.intent_type == "SECURITY_TRADE"
            }
            drift_analysis = compute_drift_analysis(
                before=before,
                after=after,
                reference_model=reference_model_validated,
                traded_instruments=traded_instruments,
                options=options,
            )

    suitability = None
    if options.enable_suitability_scanner:
        suitability = compute_suitability_result(
            before=before,
            after=after,
            shelf=shelf,
            options=options,
            portfolio_snapshot_id=portfolio.snapshot_id or portfolio.portfolio_id,
            market_data_snapshot_id=market_data.snapshot_id or "md",
            proposed_trades=trades,
        )
    gate_decision = None
    if options.enable_workflow_gates:
        gate_decision = evaluate_gate_decision(
            status=final_status,
            rule_results=rule_results,
            suitability=suitability,
            diagnostics=diagnostics,
            options=options,
            default_requires_client_consent=True,
        )

    return ProposalResult(
        proposal_run_id=run_id,
        correlation_id=correlation_id,
        status=final_status,
        before=before,
        intents=intents,
        after_simulated=after,
        reconciliation=reconciliation,
        rule_results=rule_results,
        diagnostics=diagnostics,
        drift_analysis=drift_analysis,
        suitability=suitability,
        gate_decision=gate_decision,
        explanation={"summary": final_status},
        lineage=LineageData(
            portfolio_snapshot_id=portfolio.snapshot_id or portfolio.portfolio_id,
            market_data_snapshot_id=market_data.snapshot_id or "md",
            request_hash=request_hash,
            idempotency_key=idempotency_key,
            engine_version="0.1.0",
            simulation_contract_version=simulation_contract_version,
        ),
    )
