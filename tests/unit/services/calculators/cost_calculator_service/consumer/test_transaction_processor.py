# tests/unit/services/calculators/cost_calculator_service/consumer/test_transaction_processor.py
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from cost_engine.domain.models.transaction import (
    Transaction,
)
from cost_engine.processing.cost_basis_strategies import (
    FIFOBasisStrategy,
)
from cost_engine.processing.cost_calculator import (
    CostCalculator,
)
from cost_engine.processing.cost_objects import OpenLotState
from cost_engine.processing.disposition_engine import (
    DispositionEngine,
)
from cost_engine.processing.error_reporter import (
    ErrorReporter,
)
from cost_engine.processing.parser import (
    TransactionParser,
)
from cost_engine.processing.sorter import (
    TransactionSorter,
)

from src.services.calculators.cost_calculator_service.app.transaction_processor import (
    TransactionProcessor,
    build_transaction_processor,
)


def _transaction(transaction_id: str) -> Transaction:
    return Transaction(
        transaction_id=transaction_id,
        portfolio_id="P1",
        instrument_id="I1",
        security_id="S1",
        transaction_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
        transaction_type="BUY",
        quantity=Decimal("1"),
        gross_transaction_amount=Decimal("10"),
        trade_currency="USD",
        portfolio_base_currency="USD",
        transaction_fx_rate=Decimal("1"),
    )


def _raw_transaction(
    transaction_id: str,
    transaction_date: str,
    transaction_type: str,
    quantity: str,
    gross_amount: str,
) -> dict[str, object]:
    return {
        "transaction_id": transaction_id,
        "portfolio_id": "P1",
        "instrument_id": "I1",
        "security_id": "S1",
        "transaction_date": transaction_date,
        "transaction_type": transaction_type,
        "quantity": quantity,
        "price": "1",
        "gross_transaction_amount": gross_amount,
        "trade_currency": "USD",
        "portfolio_base_currency": "USD",
        "transaction_fx_rate": "1",
        "trade_fee": "0",
    }


@pytest.fixture
def transaction_processor() -> TransactionProcessor:
    """Provides a fully wired instance of the TransactionProcessor with real components."""
    error_reporter = ErrorReporter()
    parser = TransactionParser(error_reporter=error_reporter)
    sorter = TransactionSorter()
    strategy = FIFOBasisStrategy()
    disposition_engine = DispositionEngine(cost_basis_strategy=strategy)
    cost_calculator = CostCalculator(
        disposition_engine=disposition_engine, error_reporter=error_reporter
    )
    return TransactionProcessor(
        parser=parser,
        sorter=sorter,
        disposition_engine=disposition_engine,
        cost_calculator=cost_calculator,
        error_reporter=error_reporter,
    )


def test_transaction_processor_handles_backdated_insert(
    transaction_processor: TransactionProcessor,
):
    """
    GIVEN an existing BUY and SELL, and a new back-dated BUY transaction
    WHEN the transactions are processed
    THEN the entire history should be recalculated correctly
    AND only the three processed transactions should be returned with correct P&L.
    """
    # ARRANGE
    # Existing history: Buy 100 @ $10, then Sell 50 @ $12. P&L = (50*12) - (50*10) = $100
    existing_transactions_raw = [
        {
            "transaction_id": "BUY_1",
            "portfolio_id": "P1",
            "instrument_id": "I1",
            "security_id": "S1",
            "transaction_date": "2023-01-01T10:00:00Z",
            "transaction_type": "BUY",
            "quantity": 100,
            "price": 10,
            "gross_transaction_amount": 1000,
            "trade_currency": "USD",
            "portfolio_base_currency": "USD",
            "transaction_fx_rate": 1.0,
        },
        {
            "transaction_id": "SELL_1",
            "portfolio_id": "P1",
            "instrument_id": "I1",
            "security_id": "S1",
            "transaction_date": "2023-01-10T10:00:00Z",
            "transaction_type": "SELL",
            "quantity": 50,
            "price": 12,
            "gross_transaction_amount": 600,
            "trade_currency": "USD",
            "portfolio_base_currency": "USD",
            "transaction_fx_rate": 1.0,
        },
    ]

    # New transaction: A BUY that occurred before the original SELL
    new_transactions_raw = [
        {
            "transaction_id": "BUY_2_BACKDATED",
            "portfolio_id": "P1",
            "instrument_id": "I1",
            "security_id": "S1",
            "transaction_date": "2023-01-05T10:00:00Z",
            "transaction_type": "BUY",
            "quantity": 100,
            "price": 8,
            "gross_transaction_amount": 800,
            "trade_currency": "USD",
            "portfolio_base_currency": "USD",
            "transaction_fx_rate": 1.0,
        }
    ]

    # Combine all transactions for the engine to process
    all_transactions_raw = existing_transactions_raw + new_transactions_raw

    # ACT
    # The engine processes the full list and is responsible for sorting and calculating
    processed_txns, errored_txns, open_lot_states = transaction_processor.process_transactions(
        existing_transactions_raw=[],  # Simulating a full recalculation call
        new_transactions_raw=all_transactions_raw,
    )

    # ASSERT
    assert not errored_txns
    assert len(processed_txns) == 3

    # Convert to dict for easier lookup
    results = {txn.transaction_id: txn for txn in processed_txns}

    # New Timeline: BUY_1 (@$10), BUY_2_BACKDATED (@$8), SELL_1 (@$12)
    # The SELL of 50 shares should now be matched against the first 50 shares of BUY_1.
    # P&L = (50 * $12) - (50 * $10) = $100. The back-dated buy doesn't affect this specific sell.
    assert results["SELL_1"].realized_gain_loss == Decimal("100")

    # Check that the costs for the buy transactions are correct
    assert results["BUY_1"].net_cost == Decimal("1000")
    assert results["BUY_2_BACKDATED"].net_cost == Decimal("800")
    assert results["BUY_1"].realized_gain_loss == Decimal("0")
    assert results["BUY_2_BACKDATED"].realized_gain_loss == Decimal("0")
    assert open_lot_states == {
        "BUY_1": OpenLotState(
            quantity=Decimal("50"),
            cost_local=Decimal("500"),
            cost_base=Decimal("500"),
        ),
        "BUY_2_BACKDATED": OpenLotState(
            quantity=Decimal("100"),
            cost_local=Decimal("800"),
            cost_base=Decimal("800"),
        ),
    }


@pytest.mark.parametrize("cost_basis_method", ["FIFO", "AVCO"])
def test_increment_from_open_lot_checkpoint_matches_full_history(
    cost_basis_method: str,
) -> None:
    prefix = [
        _raw_transaction("BUY-1", "2026-01-01T10:00:00+00:00", "BUY", "10", "100"),
        _raw_transaction("BUY-2", "2026-01-02T10:00:00+00:00", "BUY", "20", "240"),
        _raw_transaction("SELL-1", "2026-01-03T10:00:00+00:00", "SELL", "5", "75"),
    ]
    appended_sell = _raw_transaction("SELL-2", "2026-01-04T10:00:00+00:00", "SELL", "10", "160")
    prefix_processed, prefix_errors, prefix_states = build_transaction_processor(
        cost_basis_method
    ).process_transactions([], prefix)
    assert prefix_errors == []

    source_by_id = {row["transaction_id"]: row for row in prefix}
    checkpoint = []
    for source_transaction_id, state in prefix_states.items():
        source = dict(source_by_id[source_transaction_id])
        source["quantity"] = state.quantity
        source["gross_transaction_amount"] = state.cost_local
        source["net_cost_local"] = state.cost_local
        source["net_cost"] = state.cost_base
        checkpoint.append(source)

    incremental_processed, incremental_errors, incremental_states = build_transaction_processor(
        cost_basis_method
    ).process_increment(
        initial_open_lots_raw=checkpoint,
        new_transactions_raw=[appended_sell],
    )
    full_processed, full_errors, full_states = build_transaction_processor(
        cost_basis_method
    ).process_transactions([], [*prefix, appended_sell])

    assert incremental_errors == full_errors == []
    assert [transaction.transaction_id for transaction in incremental_processed] == ["SELL-2"]
    full_sell = next(
        transaction for transaction in full_processed if transaction.transaction_id == "SELL-2"
    )
    incremental_sell = incremental_processed[0]
    assert incremental_sell.net_cost_local == full_sell.net_cost_local
    assert incremental_sell.net_cost == full_sell.net_cost
    assert incremental_sell.realized_gain_loss_local == full_sell.realized_gain_loss_local
    assert incremental_sell.realized_gain_loss == full_sell.realized_gain_loss
    assert sum((state.quantity for state in incremental_states.values()), Decimal(0)) == sum(
        (state.quantity for state in full_states.values()), Decimal(0)
    )
    assert sum((state.cost_local for state in incremental_states.values()), Decimal(0)) == sum(
        (state.cost_local for state in full_states.values()), Decimal(0)
    )
    assert sum((state.cost_base for state in incremental_states.values()), Decimal(0)) == sum(
        (state.cost_base for state in full_states.values()), Decimal(0)
    )
    for source_transaction_id, full_state in full_states.items():
        incremental_state = incremental_states[source_transaction_id]
        assert abs(incremental_state.quantity - full_state.quantity) <= Decimal("0.0000000001")
        assert incremental_state.cost_local == full_state.cost_local
        assert incremental_state.cost_base == full_state.cost_base
    assert len(prefix_processed) == 3


@patch(
    "src.services.calculators.cost_calculator_service.app.transaction_processor.RECALCULATION_DURATION_SECONDS"
)
@patch(
    "src.services.calculators.cost_calculator_service.app.transaction_processor.RECALCULATION_DEPTH"
)
def test_transaction_processor_records_metrics(
    mock_depth_metric, mock_duration_metric, transaction_processor: TransactionProcessor
):
    """
    GIVEN a set of transactions
    WHEN process_transactions is called
    THEN it should observe the correct depth and duration values in the Prometheus metrics.
    """
    # ARRANGE
    transactions_raw = [
        {
            "transaction_id": "BUY_1",
            "portfolio_id": "P1",
            "instrument_id": "I1",
            "security_id": "S1",
            "transaction_date": "2023-01-01T10:00:00Z",
            "transaction_type": "BUY",
            "quantity": 100,
            "price": 10,
            "gross_transaction_amount": 1000,
            "trade_currency": "USD",
            "portfolio_base_currency": "USD",
        },
        {
            "transaction_id": "SELL_1",
            "portfolio_id": "P1",
            "instrument_id": "I1",
            "security_id": "S1",
            "transaction_date": "2023-01-10T10:00:00Z",
            "transaction_type": "SELL",
            "quantity": 50,
            "price": 12,
            "gross_transaction_amount": 600,
            "trade_currency": "USD",
            "portfolio_base_currency": "USD",
        },
    ]

    # ACT
    transaction_processor.process_transactions(
        existing_transactions_raw=[], new_transactions_raw=transactions_raw
    )

    # ASSERT
    # The depth is the total number of transactions processed (2 in this case)
    mock_depth_metric.observe.assert_called_once_with(2)
    # The duration metric should have been observed exactly once.
    mock_duration_metric.observe.assert_called_once()


def test_transaction_processor_reports_unexpected_calculator_errors():
    """
    GIVEN parser output with two valid new transactions
    WHEN the calculator raises for one transaction
    THEN the failed transaction is reported and excluded from processed output.
    """

    class _Parser:
        def __init__(self):
            self._responses = [
                [_transaction("EXISTING_OK")],
                [_transaction("NEW_OK"), _transaction("NEW_FAIL")],
            ]

        def parse_transactions(self, _raw_transactions):
            return self._responses.pop(0)

    class _Sorter:
        def sort_transactions(self, _existing_transactions, transactions):
            return list(transactions)

    class _CostCalculator:
        def calculate_transaction_costs(self, transaction):
            if transaction.transaction_id == "NEW_FAIL":
                raise RuntimeError("calculation failed")

    class _DispositionEngine:
        def get_open_lot_states(self):
            return {
                "NEW_OK": OpenLotState(
                    quantity=Decimal("1"),
                    cost_local=Decimal("10"),
                    cost_base=Decimal("10"),
                )
            }

    error_reporter = ErrorReporter()
    processor = TransactionProcessor(
        parser=_Parser(),
        sorter=_Sorter(),
        disposition_engine=_DispositionEngine(),
        cost_calculator=_CostCalculator(),
        error_reporter=error_reporter,
    )

    processed_txns, errored_txns, open_lot_states = processor.process_transactions(
        existing_transactions_raw=[{"transaction_id": "EXISTING_OK"}],
        new_transactions_raw=[
            {"transaction_id": "NEW_OK"},
            {"transaction_id": "NEW_FAIL"},
        ],
    )

    assert [txn.transaction_id for txn in processed_txns] == ["NEW_OK"]
    assert [(txn.transaction_id, txn.error_reason) for txn in errored_txns] == [
        ("NEW_FAIL", "Unexpected error: calculation failed")
    ]
    assert open_lot_states == {
        "NEW_OK": OpenLotState(
            quantity=Decimal("1"),
            cost_local=Decimal("10"),
            cost_base=Decimal("10"),
        )
    }
