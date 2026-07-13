"""Define stable rejection codes for ordinary settlement cash policy."""

from enum import StrEnum


class SettlementCashRejectionReasonCode(StrEnum):
    """Identify active ordinary settlement failures by transaction family."""

    SELL_NON_POSITIVE_NET_SETTLEMENT = "SELL_010_NON_POSITIVE_NET_SETTLEMENT"
    DIVIDEND_NON_POSITIVE_NET_SETTLEMENT = "DIVIDEND_013_NON_POSITIVE_NET_SETTLEMENT"
    INTEREST_NET_RECONCILIATION_MISMATCH = "INTEREST_015_NET_RECONCILIATION_MISMATCH"
    INTEREST_NON_POSITIVE_NET_SETTLEMENT = "INTEREST_017_NON_POSITIVE_NET_SETTLEMENT"
