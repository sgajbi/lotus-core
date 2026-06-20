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
    processed_txns, errored_txns, open_lot_quantities = transaction_processor.process_transactions(
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
    assert open_lot_quantities == {
        "BUY_1": Decimal("50"),
        "BUY_2_BACKDATED": Decimal("100"),
    }


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
        def get_open_lot_quantities(self):
            return {"NEW_OK": Decimal("1")}

    error_reporter = ErrorReporter()
    processor = TransactionProcessor(
        parser=_Parser(),
        sorter=_Sorter(),
        disposition_engine=_DispositionEngine(),
        cost_calculator=_CostCalculator(),
        error_reporter=error_reporter,
    )

    processed_txns, errored_txns, open_lot_quantities = processor.process_transactions(
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
    assert open_lot_quantities == {"NEW_OK": Decimal("1")}
