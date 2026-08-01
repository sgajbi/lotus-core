"""Plan deterministic average-cost-pool rebuilds from canonical transaction history."""

from collections.abc import Sequence

from portfolio_common.domain.calculation_lineage import CalculationLineage
from portfolio_common.domain.cost_basis_method import CostBasisMethod, normalize_cost_basis_method

from ...domain.cost_basis import (
    LOT_OPENING_BEHAVIORS,
    AverageCostPoolCheckpoint,
    AverageCostPoolRebuildPlan,
    CostBasisProcessingCheckpoint,
    CostBasisTransaction,
    build_cost_basis_engine_input,
    transaction_lot_behavior,
    transaction_order_key,
)
from ...domain.cost_basis.state_lineage import build_cost_basis_state_lineage
from ...domain.transaction import BookedTransaction
from ...ports import (
    CostBasisCalculationObserver,
    CostBasisFxRatePort,
    CostBasisReferenceDataPort,
    CostBasisTransactionStatePort,
)
from .fx_enrichment import enrich_cost_basis_transactions_with_fx
from .timeline import build_cost_basis_timeline_processor


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

        resolved_reference_data = await reference_data.get_cost_basis_reference_data(
            portfolio_id=portfolio_id,
            security_id=security_id,
        )
        if resolved_reference_data is None:
            raise ValueError(f"Portfolio {portfolio_id} was not found")
        portfolio = resolved_reference_data.portfolio
        cost_basis_method = normalize_cost_basis_method(portfolio.cost_basis_method)
        if cost_basis_method is not CostBasisMethod.AVCO:
            raise ValueError("Average cost pool rebuild requires an AVCO portfolio")

        instrument = resolved_reference_data.instrument
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
        processing_checkpoint = CostBasisProcessingCheckpoint.from_transaction(
            latest_transaction,
            cost_basis_method=CostBasisMethod.AVCO,
        )
        return AverageCostPoolRebuildPlan(
            checkpoint=checkpoint,
            processing_checkpoint=processing_checkpoint,
            replay_lineage=_rebuild_replay_lineage(
                history=history,
                processed=processed,
                checkpoint=checkpoint,
                processing_checkpoint=processing_checkpoint,
            ),
            source_transactions=source_transactions,
            source_states=source_states,
        )


def _rebuild_replay_lineage(
    *,
    history: Sequence[BookedTransaction],
    processed: Sequence[CostBasisTransaction],
    checkpoint: AverageCostPoolCheckpoint,
    processing_checkpoint: CostBasisProcessingCheckpoint,
) -> CalculationLineage:
    """Bind canonical persisted history to its deterministic AVCO replay result."""

    replayed_transactions: list[dict[str, object]] = []
    for sequence, transaction in enumerate(processed):
        transaction_id = str(getattr(transaction, "transaction_id", ""))
        lineage = getattr(transaction, "calculation_lineage", None)
        if not isinstance(lineage, CalculationLineage):
            raise ValueError(f"Replayed transaction lacks lineage: {transaction_id}")
        replayed_transactions.append(
            {
                "calculation_lineage": lineage.lineage_payload(),
                "sequence": sequence,
                "transaction_id": transaction_id,
            }
        )

    return build_cost_basis_state_lineage(
        algorithm_id="average-cost-pool-replay",
        input_payload={
            "canonical_history": [
                {
                    "calculation_lineage": (
                        transaction.calculation_lineage.lineage_payload()
                        if transaction.calculation_lineage is not None
                        else None
                    ),
                    "sequence": sequence,
                    "transaction_date": transaction.transaction_date.isoformat(),
                    "transaction_id": transaction.transaction_id,
                    "transaction_type": transaction.transaction_type,
                }
                for sequence, transaction in enumerate(history)
            ]
        },
        output_payload={
            "checkpoint": {
                "cost_base": checkpoint.cost_base,
                "cost_local": checkpoint.cost_local,
                "quantity": checkpoint.quantity,
                "representative_source_transaction_id": (
                    checkpoint.representative_source_transaction_id
                ),
            },
            "processing_checkpoint": {
                "calculation_state_version": (processing_checkpoint.calculation_state_version),
                "latest_transaction_id": processing_checkpoint.latest_transaction_id,
            },
            "replayed_transactions": replayed_transactions,
        },
    )
