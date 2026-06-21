from collections.abc import Mapping, Sequence
from typing import TypeAlias, TypeGuard

from src.services.query_service.app.advisory_simulation.models import (
    FxSpotIntent,
    SecurityTradeIntent,
)

ProposalIntent: TypeAlias = SecurityTradeIntent | FxSpotIntent


def _is_security_trade_side(
    intent: ProposalIntent,
    side: str,
) -> TypeGuard[SecurityTradeIntent]:
    return intent.intent_type == "SECURITY_TRADE" and intent.side == side


def _intent_currency(intent: SecurityTradeIntent) -> str | None:
    return intent.notional.currency if intent.notional is not None else None


def _same_currency_sell_dependencies(
    intents: Sequence[ProposalIntent],
    *,
    enabled: bool,
) -> dict[str, str]:
    if not enabled:
        return {}
    return {
        currency: intent.intent_id
        for intent in intents
        if _is_security_trade_side(intent, "SELL")
        if (currency := _intent_currency(intent)) is not None
    }


def _buy_security_intents(intents: Sequence[ProposalIntent]) -> list[SecurityTradeIntent]:
    return [intent for intent in intents if _is_security_trade_side(intent, "BUY")]


def _append_dependency_once(intent: SecurityTradeIntent, dependency_id: str | None) -> None:
    if dependency_id is not None and dependency_id not in intent.dependencies:
        intent.dependencies.append(dependency_id)


def _link_buy_intent_dependencies(
    *,
    intent: SecurityTradeIntent,
    fx_dependencies: Mapping[str, str],
    sell_dependencies: Mapping[str, str],
) -> None:
    currency = _intent_currency(intent)
    if currency is None:
        return
    _append_dependency_once(intent, fx_dependencies.get(currency))
    _append_dependency_once(intent, sell_dependencies.get(currency))


def link_buy_intent_dependencies(
    intents: Sequence[ProposalIntent],
    *,
    fx_intent_id_by_currency: Mapping[str, str] | None = None,
    include_same_currency_sell_dependency: bool = False,
) -> None:
    """Attach deterministic dependencies to BUY security intents in-place."""
    fx_dependencies = dict(fx_intent_id_by_currency or {})
    sell_dependencies = _same_currency_sell_dependencies(
        intents,
        enabled=include_same_currency_sell_dependency,
    )

    for intent in _buy_security_intents(intents):
        _link_buy_intent_dependencies(
            intent=intent,
            fx_dependencies=fx_dependencies,
            sell_dependencies=sell_dependencies,
        )
