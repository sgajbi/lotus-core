"""Plan deterministic average-cost-pool rebuilds from canonical transaction history."""

from portfolio_common.domain.cost_basis_method import CostBasisMethod, normalize_cost_basis_method

from ...domain.cost_basis import (
    LOT_OPENING_BEHAVIORS,
    AverageCostPoolCheckpoint,
    AverageCostPoolRebuildPlan,
    CostBasisProcessingCheckpoint,
    build_cost_basis_engine_input,
    transaction_lot_behavior,
    transaction_order_key,
)
from ...ports import (
    CostBasisCalculationObserver,
    CostBasisFxRatePort,
    CostBasisReferenceDataPort,
    CostBasisTransactionStatePort,
)
from ..cost_basis_timeline import build_cost_basis_timeline_processor
from .fx_enrichment import enrich_cost_basis_transactions_with_fx


class AverageCostPoolRebuildPlanner:
    """Replay canonical AVCO history into one validated rebuild plan."""

    def __init__(self, observer: CostBasisCalculationObserver | None = None) -> None:
        self._observer = observer

    async def build(
        self,
        *,
        portfolio_id: str,
        security_id: str,
        transactions: CostBasisTransactionStatePort,
        reference_data: CostBasisReferenceDataPort,
        fx_rates: CostBasisFxRatePort,
    ) -> AverageCostPoolRebuildPlan:
        """Build the expected AVCO source state without persisting it."""

        portfolio = await reference_data.get_cost_basis_portfolio(portfolio_id)
        if portfolio is None:
            raise ValueError(f"Portfolio {portfolio_id} was not found")
        cost_basis_method = normalize_cost_basis_method(portfolio.cost_basis_method)
        if cost_basis_method is not CostBasisMethod.AVCO:
            raise ValueError("Average cost pool rebuild requires an AVCO portfolio")

        instrument = await reference_data.get_cost_basis_instrument(security_id)
        if instrument is None:
            raise ValueError(f"Instrument {security_id} was not found")
        history = await transactions.get_transaction_history(
            portfolio_id=portfolio_id,
            security_id=security_id,
        )
        if not history:
            raise ValueError("Average cost pool rebuild requires transaction history")

        history_raw = [build_cost_basis_engine_input(transaction) for transaction in history]
        for transaction_raw in history_raw:
            transaction_raw["product_type"] = instrument.product_type
            transaction_raw["asset_class"] = instrument.asset_class
        enriched_history = await enrich_cost_basis_transactions_with_fx(
            transactions=history_raw,
            portfolio_base_currency=portfolio.base_currency,
            fx_rates=fx_rates,
        )
        processed, errored, source_states = build_cost_basis_timeline_processor(
            CostBasisMethod.AVCO,
            observer=self._observer,
        ).process_transactions(existing_transactions_raw=[], new_transactions_raw=enriched_history)
        if errored:
            first_error = errored[0]
            raise ValueError(
                f"Cost-basis calculation failed for {first_error.transaction_id}: "
                f"{first_error.error_reason}"
            )

        latest_transaction = max(processed, key=transaction_order_key)
        source_transactions = tuple(
            transaction
            for transaction in processed
            if transaction_lot_behavior(transaction.transaction_type) in LOT_OPENING_BEHAVIORS
        )
        checkpoint = AverageCostPoolCheckpoint.from_open_lot_states(
            portfolio_id=portfolio_id,
            instrument_id=latest_transaction.instrument_id,
            security_id=security_id,
            states_by_source_transaction_id=source_states,
        )
        return AverageCostPoolRebuildPlan(
            checkpoint=checkpoint,
            processing_checkpoint=CostBasisProcessingCheckpoint.from_transaction(
                latest_transaction,
                cost_basis_method=CostBasisMethod.AVCO,
            ),
            source_transactions=source_transactions,
            source_states=source_states,
        )
