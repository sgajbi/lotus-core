from decimal import Decimal
from typing import Any, Optional, TypedDict

from src.services.query_service.app.advisory_simulation.common.simulation_shared import (
    apply_fx_spot_to_portfolio,
    ensure_cash_balance,
    quantize_amount_for_currency,
)
from src.services.query_service.app.advisory_simulation.models import (
    FundingPlanEntry,
    FxSpotIntent,
    InsufficientCashEntry,
    IntentRationale,
)
from src.services.query_service.app.advisory_simulation.valuation import get_fx_rate


class _FundingSelection(TypedDict):
    pair: str
    rate: Decimal
    funding_currency: str
    sell_required: Decimal


class _FundingDeficit(TypedDict):
    currency: str
    deficit: Decimal


def record_missing_fx_pair(diagnostics: Any, pair: str) -> None:
    if pair not in diagnostics.missing_fx_pairs:
        diagnostics.missing_fx_pairs.append(pair)
    if pair not in diagnostics.data_quality["fx_missing"]:
        diagnostics.data_quality["fx_missing"].append(pair)


def funding_priority_currencies(
    *, options: Any, base_currency: str, target_currency: str, cash_ledger: dict[str, Decimal]
) -> list[str]:
    if options.fx_funding_source_currency == "BASE_ONLY":
        if base_currency != target_currency:
            return [base_currency]
        return []

    candidates = [base_currency] if base_currency != target_currency else []
    other = sorted(c for c in cash_ledger.keys() if c not in {base_currency, target_currency})
    return candidates + other


def build_auto_funding_plan(
    *,
    after_portfolio: Any,
    market_data: Any,
    options: Any,
    buy_intents: list[Any],
    diagnostics: Any,
) -> tuple[
    list[FxSpotIntent],
    dict[str, str],
    set[str],
    list[str],
    bool,
]:
    fx_intents: list[FxSpotIntent] = []
    fx_by_currency: dict[str, str] = {}
    unfunded_currencies: set[str] = set()
    hard_failures: list[str] = []
    force_pending_review = False

    if not options.auto_funding or options.funding_mode != "AUTO_FX":
        return (
            fx_intents,
            fx_by_currency,
            unfunded_currencies,
            hard_failures,
            force_pending_review,
        )

    grouped_buys: dict[str, list[Any]] = {}
    for intent in buy_intents:
        grouped_buys.setdefault(intent.notional.currency, []).append(intent)

    for target_currency in sorted(grouped_buys.keys()):
        buys = grouped_buys[target_currency]
        required = sum((intent.notional.amount for intent in buys), Decimal("0"))
        available_before_fx = ensure_cash_balance(after_portfolio, target_currency).amount
        fx_needed = max(Decimal("0"), required - available_before_fx)

        plan = FundingPlanEntry(
            target_currency=target_currency,
            required=quantize_amount_for_currency(required, target_currency),
            available_before_fx=quantize_amount_for_currency(available_before_fx, target_currency),
            fx_needed=quantize_amount_for_currency(fx_needed, target_currency),
            fx_pair=None,
            funding_currency=None,
        )

        if fx_needed <= Decimal("0"):
            diagnostics.funding_plan.append(plan)
            continue

        cash_ledger = {entry.currency: entry.amount for entry in after_portfolio.cash_balances}
        candidates = funding_priority_currencies(
            options=options,
            base_currency=after_portfolio.base_currency,
            target_currency=target_currency,
            cash_ledger=cash_ledger,
        )

        selected: Optional[_FundingSelection] = None
        smallest_deficit: Optional[_FundingDeficit] = None
        for funding_currency in candidates:
            pair = f"{target_currency}/{funding_currency}"
            rate = get_fx_rate(market_data, target_currency, funding_currency)
            if rate is None:
                record_missing_fx_pair(diagnostics, pair)
                continue

            sell_required = quantize_amount_for_currency(
                fx_needed * rate,
                funding_currency,
            )
            available_funding = ensure_cash_balance(after_portfolio, funding_currency).amount

            if available_funding >= sell_required:
                selected = {
                    "pair": pair,
                    "rate": rate,
                    "funding_currency": funding_currency,
                    "sell_required": sell_required,
                }
                break

            deficit = sell_required - available_funding
            if smallest_deficit is None or deficit < smallest_deficit["deficit"]:
                smallest_deficit = {
                    "currency": funding_currency,
                    "deficit": deficit,
                }

        if selected is None:
            if diagnostics.missing_fx_pairs and not options.block_on_missing_fx:
                force_pending_review = True
                if "PROPOSAL_MISSING_FX_NON_BLOCKING" not in diagnostics.warnings:
                    diagnostics.warnings.append("PROPOSAL_MISSING_FX_NON_BLOCKING")
                unfunded_currencies.add(target_currency)
                diagnostics.funding_plan.append(plan)
                continue

            if diagnostics.missing_fx_pairs and options.block_on_missing_fx:
                hard_failures.append("PROPOSAL_MISSING_FX_FOR_FUNDING")
                unfunded_currencies.add(target_currency)
                diagnostics.funding_plan.append(plan)
                continue

            if smallest_deficit is not None:
                diagnostics.insufficient_cash.append(
                    InsufficientCashEntry(
                        currency=smallest_deficit["currency"],
                        deficit=quantize_amount_for_currency(
                            smallest_deficit["deficit"],
                            smallest_deficit["currency"],
                        ),
                    )
                )
            hard_failures.append("PROPOSAL_INSUFFICIENT_FUNDING_CASH")
            unfunded_currencies.add(target_currency)
            diagnostics.funding_plan.append(plan)
            continue

        fx_intent_id = f"oi_fx_{len(fx_intents) + 1}"
        fx_buy_amount = quantize_amount_for_currency(fx_needed, target_currency)
        fx_intent = FxSpotIntent(
            intent_id=fx_intent_id,
            pair=selected["pair"],
            buy_currency=target_currency,
            buy_amount=fx_buy_amount,
            sell_currency=selected["funding_currency"],
            sell_amount_estimated=selected["sell_required"],
            dependencies=[],
            rationale=IntentRationale(code="FUNDING", message=f"Fund {target_currency} buys"),
        )

        apply_fx_spot_to_portfolio(after_portfolio, fx_intent)
        fx_intents.append(fx_intent)
        fx_by_currency[target_currency] = fx_intent_id

        plan.fx_pair = selected["pair"]
        plan.funding_currency = selected["funding_currency"]
        diagnostics.funding_plan.append(plan)

    return (
        fx_intents,
        fx_by_currency,
        unfunded_currencies,
        hard_failures,
        force_pending_review,
    )
