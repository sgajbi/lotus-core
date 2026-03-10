from ..domain.models.transaction import Transaction


class TransactionSorter:
    """
    Responsible for merging and sorting transactions according to processing rules.
    """

    def sort_transactions(
        self, existing_transactions: list[Transaction], new_transactions: list[Transaction]
    ) -> list[Transaction]:
        """
        Merges and sorts transactions.
        Sorting Rules:
        1. Primary sort: transaction_date ascending.
        2. Bundle A dependency rank (source-out, target-in, cash-consideration, other).
        3. Bundle A target sequence and target instrument fallback.
        4. Quantity descending for non-Bundle-A tie cases.
        5. Stable transaction_id tiebreak.
        """
        all_transactions = existing_transactions + new_transactions
        all_transactions.sort(
            key=lambda txn: (
                txn.transaction_date,
                _ca_bundle_a_dependency_rank(txn),
                *_ca_bundle_a_target_order_key(txn),
                -txn.quantity,
                txn.transaction_id,
            )
        )
        return all_transactions


def _ca_bundle_a_dependency_rank(txn: Transaction) -> int:
    transaction_type = str(getattr(txn, "transaction_type", "") or "").upper()
    if transaction_type in {"SPIN_OFF", "DEMERGER_OUT"}:
        return 0
    if transaction_type in {"RIGHTS_ANNOUNCE", "RIGHTS_ALLOCATE"}:
        return 0
    if transaction_type in {"SPIN_IN", "DEMERGER_IN"}:
        return 1
    if transaction_type in {
        "RIGHTS_SUBSCRIBE",
        "RIGHTS_OVERSUBSCRIBE",
        "RIGHTS_SELL",
        "RIGHTS_EXPIRE",
        "RIGHTS_ADJUSTMENT",
    }:
        return 1
    if transaction_type == "CASH_CONSIDERATION":
        return 2
    if transaction_type == "RIGHTS_SHARE_DELIVERY":
        return 2
    if transaction_type == "RIGHTS_REFUND":
        return 3
    return 4


def _ca_bundle_a_target_order_key(txn: Transaction) -> tuple[int, str]:
    child_sequence_hint = getattr(txn, "child_sequence_hint", None)
    target_instrument_id = str(getattr(txn, "target_instrument_id", "") or "")
    sequence = int(child_sequence_hint) if child_sequence_hint is not None else 2_147_483_647
    return (sequence, target_instrument_id)
