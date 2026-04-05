from collections.abc import Mapping, Sequence
from typing import TypeAlias

from src.services.query_service.app.advisory_simulation.models import (
    FxSpotIntent,
    SecurityTradeIntent,
)

ProposalIntent: TypeAlias = SecurityTradeIntent | FxSpotIntent


def link_buy_intent_dependencies(
    intents: Sequence[ProposalIntent],
    *,
    fx_intent_id_by_currency: Mapping[str, str] | None = None,
    include_same_currency_sell_dependency: bool = False,
) -> None:
    """Attach deterministic dependencies to BUY security intents in-place."""
    fx_dependencies = dict(fx_intent_id_by_currency or {})

    sell_intent_id_by_currency: dict[str, str] = {}
    if include_same_currency_sell_dependency:
        for intent in intents:
            if intent.intent_type == "SECURITY_TRADE" and intent.side == "SELL":
                if intent.notional is None:
                    continue
                sell_intent_id_by_currency[intent.notional.currency] = intent.intent_id

    for intent in intents:
        if intent.intent_type != "SECURITY_TRADE" or intent.side != "BUY":
            continue

        if intent.notional is None:
            continue
        currency = intent.notional.currency
        fx_dependency = fx_dependencies.get(currency)
        if fx_dependency is not None and fx_dependency not in intent.dependencies:
            intent.dependencies.append(fx_dependency)

        if not include_same_currency_sell_dependency:
            continue

        sell_dependency = sell_intent_id_by_currency.get(currency)
        if sell_dependency is not None and sell_dependency not in intent.dependencies:
            intent.dependencies.append(sell_dependency)
