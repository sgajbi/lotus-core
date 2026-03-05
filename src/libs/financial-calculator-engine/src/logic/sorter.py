# libs/financial-calculator-engine/src/logic/sorter.py
from core.models.transaction import Transaction


class TransactionSorter:
    """
    Responsible for merging and sorting transactions according to processing rules.
    """
    def sort_transactions(
        self,
        existing_transactions: list[Transaction],
        new_transactions: list[Transaction]
    ) -> list[Transaction]:
        """
        Merges and sorts transactions.
        Sorting Rules:
        1. Primary sort: transaction_date ascending.
        2. Secondary sort: quantity descending.
        """
        all_transactions = existing_transactions + new_transactions
        all_transactions.sort(key=lambda txn: (txn.transaction_date, -txn.quantity))
        return all_transactions