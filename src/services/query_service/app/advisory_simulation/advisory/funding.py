from decimal import Decimal
from typing import Any, Optional, TypeAlias, TypedDict

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


_AutoFundingResult: TypeAlias = tuple[
    list[FxSpotIntent],
    dict[str, str],
    set[str],
    list[str],
    bool,
]


def record_missing_fx_pair(diagnostics: Any, pair: str) -> None:
    if pair not in diagnostics.missing_fx_pairs:
        diagnostics.missing_fx_pairs.append(pair)
    if pair not in diagnostics.data_quality["fx_missing"]:
        diagnostics.data_quality["fx_missing"].append(pair)


def funding_priority_currencies(
    *, options: Any, base_currency: str, target_currency: str, cash_ledger: dict[str, Decimal]
) -> list[str]:
    if options.fx_funding_source_currency == "BASE_ONLY":
        return _base_currency_candidates(base_currency, target_currency)

    return _base_currency_candidates(base_currency, target_currency) + _other_cash_currencies(
        cash_ledger=cash_ledger,
        base_currency=base_currency,
        target_currency=target_currency,
    )


def _base_currency_candidates(base_currency: str, target_currency: str) -> list[str]:
    return [base_currency] if base_currency != target_currency else []


def _other_cash_currencies(
    *,
    cash_ledger: dict[str, Decimal],
    base_currency: str,
    target_currency: str,
) -> list[str]:
    return sorted(c for c in cash_ledger.keys() if c not in {base_currency, target_currency})


def _empty_auto_funding_result() -> _AutoFundingResult:
    return [], {}, set(), [], False


def _auto_funding_enabled(options: Any) -> bool:
    return bool(options.auto_funding and options.funding_mode == "AUTO_FX")


def _group_buys_by_currency(buy_intents: list[Any]) -> dict[str, list[Any]]:
    grouped_buys: dict[str, list[Any]] = {}
    for intent in buy_intents:
        grouped_buys.setdefault(intent.notional.currency, []).append(intent)
    return grouped_buys


def _required_notional(buys: list[Any]) -> Decimal:
    return sum((intent.notional.amount for intent in buys), Decimal("0"))


def _cash_ledger(after_portfolio: Any) -> dict[str, Decimal]:
    return {entry.currency: entry.amount for entry in after_portfolio.cash_balances}


def _build_funding_plan_entry(
    *,
    target_currency: str,
    required: Decimal,
    available_before_fx: Decimal,
    fx_needed: Decimal,
) -> FundingPlanEntry:
    return FundingPlanEntry(
        target_currency=target_currency,
        required=quantize_amount_for_currency(required, target_currency),
        available_before_fx=quantize_amount_for_currency(available_before_fx, target_currency),
        fx_needed=quantize_amount_for_currency(fx_needed, target_currency),
        fx_pair=None,
        funding_currency=None,
    )


def _funding_candidates(
    *,
    after_portfolio: Any,
    options: Any,
    target_currency: str,
) -> list[str]:
    return funding_priority_currencies(
        options=options,
        base_currency=after_portfolio.base_currency,
        target_currency=target_currency,
        cash_ledger=_cash_ledger(after_portfolio),
    )


def _deficit_entry(currency: str, deficit: Decimal) -> _FundingDeficit:
    return {"currency": currency, "deficit": deficit}


def _candidate_selection(
    *,
    funding_currency: str,
    target_currency: str,
    fx_needed: Decimal,
    market_data: Any,
    after_portfolio: Any,
    diagnostics: Any,
) -> tuple[Optional[_FundingSelection], Optional[_FundingDeficit]]:
    pair = f"{target_currency}/{funding_currency}"
    rate = get_fx_rate(market_data, target_currency, funding_currency)
    if rate is None:
        record_missing_fx_pair(diagnostics, pair)
        return None, None

    sell_required = quantize_amount_for_currency(fx_needed * rate, funding_currency)
    available_funding = ensure_cash_balance(after_portfolio, funding_currency).amount
    if available_funding >= sell_required:
        return (
            {
                "pair": pair,
                "rate": rate,
                "funding_currency": funding_currency,
                "sell_required": sell_required,
            },
            None,
        )

    return None, _deficit_entry(funding_currency, sell_required - available_funding)


def _smaller_deficit(
    current: Optional[_FundingDeficit],
    candidate: Optional[_FundingDeficit],
) -> Optional[_FundingDeficit]:
    if candidate is None:
        return current
    if current is None or candidate["deficit"] < current["deficit"]:
        return candidate
    return current


def _select_funding(
    *,
    candidates: list[str],
    target_currency: str,
    fx_needed: Decimal,
    market_data: Any,
    after_portfolio: Any,
    diagnostics: Any,
) -> tuple[Optional[_FundingSelection], Optional[_FundingDeficit]]:
    smallest_deficit: Optional[_FundingDeficit] = None
    for funding_currency in candidates:
        selected, deficit = _candidate_selection(
            funding_currency=funding_currency,
            target_currency=target_currency,
            fx_needed=fx_needed,
            market_data=market_data,
            after_portfolio=after_portfolio,
            diagnostics=diagnostics,
        )
        if selected is not None:
            return selected, smallest_deficit
        smallest_deficit = _smaller_deficit(smallest_deficit, deficit)
    return None, smallest_deficit


def _append_funding_plan(diagnostics: Any, plan: FundingPlanEntry) -> None:
    diagnostics.funding_plan.append(plan)


def _record_unfunded_currency(unfunded_currencies: set[str], target_currency: str) -> None:
    unfunded_currencies.add(target_currency)


def _missing_fx_pairs_present(diagnostics: Any) -> bool:
    return bool(diagnostics.missing_fx_pairs)


def _handle_missing_fx_without_block(
    *,
    diagnostics: Any,
    target_currency: str,
    plan: FundingPlanEntry,
    unfunded_currencies: set[str],
) -> bool:
    if "PROPOSAL_MISSING_FX_NON_BLOCKING" not in diagnostics.warnings:
        diagnostics.warnings.append("PROPOSAL_MISSING_FX_NON_BLOCKING")
    _record_unfunded_currency(unfunded_currencies, target_currency)
    _append_funding_plan(diagnostics, plan)
    return True


def _handle_missing_fx_block(
    *,
    hard_failures: list[str],
    target_currency: str,
    plan: FundingPlanEntry,
    unfunded_currencies: set[str],
    diagnostics: Any,
) -> None:
    hard_failures.append("PROPOSAL_MISSING_FX_FOR_FUNDING")
    _record_unfunded_currency(unfunded_currencies, target_currency)
    _append_funding_plan(diagnostics, plan)


def _record_smallest_deficit(
    *,
    diagnostics: Any,
    smallest_deficit: Optional[_FundingDeficit],
) -> None:
    if smallest_deficit is None:
        return
    diagnostics.insufficient_cash.append(
        InsufficientCashEntry(
            currency=smallest_deficit["currency"],
            deficit=quantize_amount_for_currency(
                smallest_deficit["deficit"],
                smallest_deficit["currency"],
            ),
        )
    )


def _handle_insufficient_funding(
    *,
    diagnostics: Any,
    hard_failures: list[str],
    target_currency: str,
    plan: FundingPlanEntry,
    unfunded_currencies: set[str],
    smallest_deficit: Optional[_FundingDeficit],
) -> None:
    _record_smallest_deficit(diagnostics=diagnostics, smallest_deficit=smallest_deficit)
    hard_failures.append("PROPOSAL_INSUFFICIENT_FUNDING_CASH")
    _record_unfunded_currency(unfunded_currencies, target_currency)
    _append_funding_plan(diagnostics, plan)


def _handle_unselected_funding(
    *,
    diagnostics: Any,
    options: Any,
    hard_failures: list[str],
    target_currency: str,
    plan: FundingPlanEntry,
    unfunded_currencies: set[str],
    smallest_deficit: Optional[_FundingDeficit],
) -> bool:
    if _missing_fx_pairs_present(diagnostics) and not options.block_on_missing_fx:
        return _handle_missing_fx_without_block(
            diagnostics=diagnostics,
            target_currency=target_currency,
            plan=plan,
            unfunded_currencies=unfunded_currencies,
        )
    if _missing_fx_pairs_present(diagnostics) and options.block_on_missing_fx:
        _handle_missing_fx_block(
            hard_failures=hard_failures,
            target_currency=target_currency,
            plan=plan,
            unfunded_currencies=unfunded_currencies,
            diagnostics=diagnostics,
        )
        return False

    _handle_insufficient_funding(
        diagnostics=diagnostics,
        hard_failures=hard_failures,
        target_currency=target_currency,
        plan=plan,
        unfunded_currencies=unfunded_currencies,
        smallest_deficit=smallest_deficit,
    )
    return False


def _build_fx_intent(
    *,
    fx_intent_id: str,
    target_currency: str,
    fx_needed: Decimal,
    selected: _FundingSelection,
) -> FxSpotIntent:
    return FxSpotIntent(
        intent_id=fx_intent_id,
        pair=selected["pair"],
        buy_currency=target_currency,
        buy_amount=quantize_amount_for_currency(fx_needed, target_currency),
        sell_currency=selected["funding_currency"],
        sell_amount_estimated=selected["sell_required"],
        dependencies=[],
        rationale=IntentRationale(code="FUNDING", message=f"Fund {target_currency} buys"),
    )


def _apply_selected_funding(
    *,
    after_portfolio: Any,
    diagnostics: Any,
    fx_intents: list[FxSpotIntent],
    fx_by_currency: dict[str, str],
    target_currency: str,
    fx_needed: Decimal,
    selected: _FundingSelection,
    plan: FundingPlanEntry,
) -> None:
    fx_intent_id = f"oi_fx_{len(fx_intents) + 1}"
    fx_intent = _build_fx_intent(
        fx_intent_id=fx_intent_id,
        target_currency=target_currency,
        fx_needed=fx_needed,
        selected=selected,
    )

    apply_fx_spot_to_portfolio(after_portfolio, fx_intent)
    fx_intents.append(fx_intent)
    fx_by_currency[target_currency] = fx_intent_id

    plan.fx_pair = selected["pair"]
    plan.funding_currency = selected["funding_currency"]
    _append_funding_plan(diagnostics, plan)


def _target_funding_need(
    *,
    after_portfolio: Any,
    target_currency: str,
    buys: list[Any],
) -> tuple[Decimal, Decimal, Decimal, FundingPlanEntry]:
    required = _required_notional(buys)
    available_before_fx = ensure_cash_balance(after_portfolio, target_currency).amount
    fx_needed = max(Decimal("0"), required - available_before_fx)
    plan = _build_funding_plan_entry(
        target_currency=target_currency,
        required=required,
        available_before_fx=available_before_fx,
        fx_needed=fx_needed,
    )
    return required, available_before_fx, fx_needed, plan


def _process_target_currency_funding(
    *,
    after_portfolio: Any,
    market_data: Any,
    options: Any,
    diagnostics: Any,
    target_currency: str,
    buys: list[Any],
    fx_intents: list[FxSpotIntent],
    fx_by_currency: dict[str, str],
    unfunded_currencies: set[str],
    hard_failures: list[str],
) -> bool:
    _required, _available_before_fx, fx_needed, plan = _target_funding_need(
        after_portfolio=after_portfolio,
        target_currency=target_currency,
        buys=buys,
    )

    if fx_needed <= Decimal("0"):
        _append_funding_plan(diagnostics, plan)
        return False

    selected, smallest_deficit = _select_funding(
        candidates=_funding_candidates(
            after_portfolio=after_portfolio,
            options=options,
            target_currency=target_currency,
        ),
        target_currency=target_currency,
        fx_needed=fx_needed,
        market_data=market_data,
        after_portfolio=after_portfolio,
        diagnostics=diagnostics,
    )

    if selected is None:
        return _handle_unselected_funding(
            diagnostics=diagnostics,
            options=options,
            hard_failures=hard_failures,
            target_currency=target_currency,
            plan=plan,
            unfunded_currencies=unfunded_currencies,
            smallest_deficit=smallest_deficit,
        )

    _apply_selected_funding(
        after_portfolio=after_portfolio,
        diagnostics=diagnostics,
        fx_intents=fx_intents,
        fx_by_currency=fx_by_currency,
        target_currency=target_currency,
        fx_needed=fx_needed,
        selected=selected,
        plan=plan,
    )
    return False


def build_auto_funding_plan(
    *,
    after_portfolio: Any,
    market_data: Any,
    options: Any,
    buy_intents: list[Any],
    diagnostics: Any,
) -> _AutoFundingResult:
    fx_intents, fx_by_currency, unfunded_currencies, hard_failures, force_pending_review = (
        _empty_auto_funding_result()
    )

    if not _auto_funding_enabled(options):
        return fx_intents, fx_by_currency, unfunded_currencies, hard_failures, force_pending_review

    grouped_buys = _group_buys_by_currency(buy_intents)

    for target_currency in sorted(grouped_buys.keys()):
        pending_review = _process_target_currency_funding(
            after_portfolio=after_portfolio,
            market_data=market_data,
            options=options,
            diagnostics=diagnostics,
            target_currency=target_currency,
            buys=grouped_buys[target_currency],
            fx_intents=fx_intents,
            fx_by_currency=fx_by_currency,
            unfunded_currencies=unfunded_currencies,
            hard_failures=hard_failures,
        )
        force_pending_review = force_pending_review or pending_review

    return (
        fx_intents,
        fx_by_currency,
        unfunded_currencies,
        hard_failures,
        force_pending_review,
    )
