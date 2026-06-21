from ..domain.models.transaction import Transaction

_LAST_DEPENDENCY_RANK = 4
_DEFAULT_CASH_DEPENDENCY_RANK = 1

_CA_BUNDLE_A_DEPENDENCY_RANKS = {
    "SPIN_OFF": 0,
    "DEMERGER_OUT": 0,
    "RIGHTS_ANNOUNCE": 0,
    "RIGHTS_ALLOCATE": 0,
    "SPIN_IN": 1,
    "DEMERGER_IN": 1,
    "RIGHTS_SUBSCRIBE": 1,
    "RIGHTS_OVERSUBSCRIBE": 1,
    "RIGHTS_SELL": 1,
    "RIGHTS_EXPIRE": 1,
    "RIGHTS_ADJUSTMENT": 1,
    "CASH_CONSIDERATION": 2,
    "RIGHTS_SHARE_DELIVERY": 2,
    "RIGHTS_REFUND": 3,
}

_CASH_INFLOW_COMPONENT_TYPES = frozenset({"FX_CASH_SETTLEMENT_BUY"})
_CASH_INFLOW_TRANSACTION_TYPES = frozenset(
    {"DEPOSIT", "TRANSFER_IN", "MERGER_IN", "EXCHANGE_IN", "REPLACEMENT_IN", "BUY"}
)
_CASH_OUTFLOW_COMPONENT_TYPES = frozenset({"FX_CASH_SETTLEMENT_SELL"})
_CASH_OUTFLOW_TRANSACTION_TYPES = frozenset({"SELL", "WITHDRAWAL", "FEE", "TAX", "TRANSFER_OUT"})


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
                _cash_dependency_rank(txn),
                *_ca_bundle_a_target_order_key(txn),
                -txn.quantity,
                txn.transaction_id,
            )
        )
        return all_transactions


def _ca_bundle_a_dependency_rank(txn: Transaction) -> int:
    transaction_type = _normalize_sort_code(getattr(txn, "transaction_type", ""))
    return _CA_BUNDLE_A_DEPENDENCY_RANKS.get(transaction_type, _LAST_DEPENDENCY_RANK)


def _ca_bundle_a_target_order_key(txn: Transaction) -> tuple[int, str]:
    child_sequence_hint = getattr(txn, "child_sequence_hint", None)
    target_instrument_id = str(getattr(txn, "target_instrument_id", "") or "")
    sequence = int(child_sequence_hint) if child_sequence_hint is not None else 2_147_483_647
    return (sequence, target_instrument_id)


def _cash_dependency_rank(txn: Transaction) -> int:
    component_type = _normalize_sort_code(getattr(txn, "component_type", ""))
    transaction_type = _normalize_sort_code(getattr(txn, "transaction_type", ""))

    if not _is_cash_transaction(txn):
        return _DEFAULT_CASH_DEPENDENCY_RANK
    if _is_cash_inflow(component_type, transaction_type):
        return 0
    if _is_cash_outflow(component_type, transaction_type):
        return 2
    return _DEFAULT_CASH_DEPENDENCY_RANK


def _is_cash_transaction(txn: Transaction) -> bool:
    product_type = _normalize_sort_code(getattr(txn, "product_type", ""))
    asset_class = _normalize_sort_code(getattr(txn, "asset_class", ""))
    instrument_id = _normalize_sort_code(getattr(txn, "instrument_id", ""))
    security_id = _normalize_sort_code(getattr(txn, "security_id", ""))
    return (
        product_type == "CASH"
        or asset_class == "CASH"
        or instrument_id.startswith("CASH")
        or security_id.startswith("CASH")
    )


def _is_cash_inflow(component_type: str, transaction_type: str) -> bool:
    return (
        component_type in _CASH_INFLOW_COMPONENT_TYPES
        or transaction_type in _CASH_INFLOW_TRANSACTION_TYPES
    )


def _is_cash_outflow(component_type: str, transaction_type: str) -> bool:
    return (
        component_type in _CASH_OUTFLOW_COMPONENT_TYPES
        or transaction_type in _CASH_OUTFLOW_TRANSACTION_TYPES
    )


def _normalize_sort_code(value: object) -> str:
    return str(value or "").strip().upper()
