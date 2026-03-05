import logging
from decimal import Decimal
from typing import Optional

from portfolio_common.database_models import Cashflow, CashflowRule
from portfolio_common.events import TransactionEvent
from portfolio_common.monitoring import CASHFLOWS_CREATED_TOTAL

from .enums import CashflowClassification

logger = logging.getLogger(__name__)

class CashflowLogic:
    """
    A stateless calculator that generates a Cashflow object from a transaction
    based on a given business rule from the database.
    """
    @staticmethod
    def calculate(
        transaction: TransactionEvent,
        rule: CashflowRule,
        epoch: Optional[int] = 0
    ) -> Cashflow:
        """
        Applies the calculation rule to a transaction to generate a cashflow.
        """
        amount = Decimal(0)

        # For NET, we adjust the gross amount by the fee.
        if transaction.transaction_type in ["BUY", "FEE"]:
            amount = transaction.gross_transaction_amount + (transaction.trade_fee or 0)
        else: # SELL, DIVIDEND, INTEREST, etc.
            amount = transaction.gross_transaction_amount - (transaction.trade_fee or 0)

        # Convention: Inflows to the portfolio are positive, outflows are negative.
        positive_classifications = [
            CashflowClassification.INVESTMENT_INFLOW,  # From a SELL
            CashflowClassification.INCOME,             # From DIVIDEND, INTEREST
            CashflowClassification.CASHFLOW_IN         # From DEPOSIT
        ]

        # INTEREST direction baseline: default INCOME (inflow), EXPENSE (outflow).
        interest_direction = str(getattr(transaction, "interest_direction", "INCOME")).upper()
        if transaction.transaction_type == "INTEREST":
            if interest_direction == "EXPENSE":
                amount = -abs(amount)
            else:
                amount = abs(amount)
        elif transaction.transaction_type == "ADJUSTMENT":
            movement_direction = str(getattr(transaction, "movement_direction", "INFLOW")).upper()
            amount = abs(amount) if movement_direction == "INFLOW" else -abs(amount)
        elif rule.classification in positive_classifications:
            amount = abs(amount)
        elif rule.classification == CashflowClassification.TRANSFER:
            if transaction.transaction_type == "TRANSFER_IN":
                amount = abs(amount)
            else: # TRANSFER_OUT
                amount = -abs(amount)
        else:
            # All other classifications are outflows (INVESTMENT_OUTFLOW, EXPENSE, CASHFLOW_OUT)
            amount = -abs(amount)

        # Create the Cashflow database object
        cashflow = Cashflow(
            transaction_id=transaction.transaction_id,
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            cashflow_date=transaction.transaction_date.date(),
            amount=amount,
            currency=transaction.currency,
            classification=rule.classification,
            timing=rule.timing,
            calculation_type="NET", # Currently all are NET
            is_position_flow=rule.is_position_flow,
            is_portfolio_flow=rule.is_portfolio_flow,
            economic_event_id=transaction.economic_event_id,
            linked_transaction_group_id=transaction.linked_transaction_group_id,
            epoch=epoch or 0
        )

        # Increment the Prometheus counter
        CASHFLOWS_CREATED_TOTAL.labels(
            classification=rule.classification,
            timing=rule.timing
        ).inc()
        
        logger.info(f"Calculated cashflow for txn {transaction.transaction_id}: Amount={amount}, Class='{rule.classification}'")
        return cashflow
