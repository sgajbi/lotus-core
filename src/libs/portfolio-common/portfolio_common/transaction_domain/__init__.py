"""Canonical transaction domain contracts and validators."""

from .buy_models import BuyCanonicalTransaction
from .buy_reason_codes import BuyValidationReasonCode
from .buy_validation import (
    BuyValidationError,
    BuyValidationIssue,
    validate_buy_transaction,
)
from .adjustment_cash_leg import (
    ADJUSTMENT_TRANSACTION_TYPE,
    AdjustmentCashLegError,
    build_auto_generated_adjustment_cash_leg,
    should_auto_generate_cash_leg,
)
from .cash_entry_mode import (
    AUTO_GENERATE_CASH_ENTRY_MODE,
    UPSTREAM_PROVIDED_CASH_ENTRY_MODE,
    is_upstream_provided_cash_entry_mode,
    normalize_cash_entry_mode,
)
from .dividend_linkage import (
    DIVIDEND_DEFAULT_POLICY_ID,
    DIVIDEND_DEFAULT_POLICY_VERSION,
    enrich_dividend_transaction_metadata,
)
from .dividend_models import DividendCanonicalTransaction
from .dividend_reason_codes import DividendValidationReasonCode
from .dividend_validation import (
    DividendValidationError,
    DividendValidationIssue,
    validate_dividend_transaction,
)
from .dual_leg_pairing import (
    DualLegPairingError,
    DualLegPairingIssue,
    assert_upstream_cash_leg_pairing,
    validate_upstream_cash_leg_pairing,
)
from .interest_linkage import (
    INTEREST_DEFAULT_POLICY_ID,
    INTEREST_DEFAULT_POLICY_VERSION,
    enrich_interest_transaction_metadata,
)
from .interest_models import InterestCanonicalTransaction
from .interest_reason_codes import InterestValidationReasonCode
from .interest_validation import (
    InterestValidationError,
    InterestValidationIssue,
    validate_interest_transaction,
)
from .sell_linkage import (
    SELL_AVCO_POLICY_ID,
    SELL_DEFAULT_POLICY_VERSION,
    SELL_FIFO_POLICY_ID,
    enrich_sell_transaction_metadata,
)
from .sell_models import SellCanonicalTransaction
from .sell_reason_codes import SellValidationReasonCode
from .sell_validation import (
    SellValidationError,
    SellValidationIssue,
    validate_sell_transaction,
)

__all__ = [
    "BuyCanonicalTransaction",
    "BuyValidationError",
    "BuyValidationIssue",
    "BuyValidationReasonCode",
    "validate_buy_transaction",
    "ADJUSTMENT_TRANSACTION_TYPE",
    "AdjustmentCashLegError",
    "should_auto_generate_cash_leg",
    "build_auto_generated_adjustment_cash_leg",
    "AUTO_GENERATE_CASH_ENTRY_MODE",
    "UPSTREAM_PROVIDED_CASH_ENTRY_MODE",
    "normalize_cash_entry_mode",
    "is_upstream_provided_cash_entry_mode",
    "DividendCanonicalTransaction",
    "DividendValidationError",
    "DividendValidationIssue",
    "DividendValidationReasonCode",
    "validate_dividend_transaction",
    "DIVIDEND_DEFAULT_POLICY_ID",
    "DIVIDEND_DEFAULT_POLICY_VERSION",
    "enrich_dividend_transaction_metadata",
    "DualLegPairingError",
    "DualLegPairingIssue",
    "validate_upstream_cash_leg_pairing",
    "assert_upstream_cash_leg_pairing",
    "InterestCanonicalTransaction",
    "InterestValidationError",
    "InterestValidationIssue",
    "InterestValidationReasonCode",
    "validate_interest_transaction",
    "INTEREST_DEFAULT_POLICY_ID",
    "INTEREST_DEFAULT_POLICY_VERSION",
    "enrich_interest_transaction_metadata",
    "SellCanonicalTransaction",
    "SellValidationError",
    "SellValidationIssue",
    "SellValidationReasonCode",
    "validate_sell_transaction",
    "SELL_AVCO_POLICY_ID",
    "SELL_FIFO_POLICY_ID",
    "SELL_DEFAULT_POLICY_VERSION",
    "enrich_sell_transaction_metadata",
]

