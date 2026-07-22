"""Protect the documented ordinary transaction validation reason-code vocabulary."""

from src.services.portfolio_transaction_processing_service.app.domain.transaction import (
    BuyValidationReasonCode,
    DividendValidationReasonCode,
    InterestValidationReasonCode,
    SellValidationReasonCode,
)


def test_buy_validation_reason_codes_remain_stable() -> None:
    assert [code.value for code in BuyValidationReasonCode] == [
        "BUY_001_INVALID_TRANSACTION_TYPE",
        "BUY_002_MISSING_SETTLEMENT_DATE",
        "BUY_003_NON_POSITIVE_QUANTITY",
        "BUY_004_NON_POSITIVE_GROSS_AMOUNT",
        "BUY_005_MISSING_TRADE_CURRENCY",
        "BUY_006_MISSING_BOOK_CURRENCY",
        "BUY_007_INVALID_DATE_ORDER",
        "BUY_008_MISSING_LINKAGE_IDENTIFIER",
        "BUY_009_MISSING_POLICY_METADATA",
    ]


def test_sell_validation_reason_codes_remain_stable() -> None:
    assert [code.value for code in SellValidationReasonCode] == [
        "SELL_001_INVALID_TRANSACTION_TYPE",
        "SELL_002_MISSING_SETTLEMENT_DATE",
        "SELL_003_NON_POSITIVE_QUANTITY",
        "SELL_004_NON_POSITIVE_GROSS_AMOUNT",
        "SELL_005_MISSING_TRADE_CURRENCY",
        "SELL_006_MISSING_BOOK_CURRENCY",
        "SELL_007_INVALID_DATE_ORDER",
        "SELL_008_MISSING_LINKAGE_IDENTIFIER",
        "SELL_009_MISSING_POLICY_METADATA",
        "SELL_010_NON_POSITIVE_NET_SETTLEMENT",
    ]


def test_dividend_validation_reason_codes_remain_stable() -> None:
    assert [code.value for code in DividendValidationReasonCode] == [
        "DIVIDEND_001_INVALID_TRANSACTION_TYPE",
        "DIVIDEND_002_MISSING_SETTLEMENT_DATE",
        "DIVIDEND_003_NON_ZERO_QUANTITY",
        "DIVIDEND_004_NON_ZERO_PRICE",
        "DIVIDEND_005_NON_POSITIVE_GROSS_AMOUNT",
        "DIVIDEND_006_MISSING_TRADE_CURRENCY",
        "DIVIDEND_007_MISSING_BOOK_CURRENCY",
        "DIVIDEND_008_INVALID_DATE_ORDER",
        "DIVIDEND_009_MISSING_LINKAGE_IDENTIFIER",
        "DIVIDEND_010_MISSING_POLICY_METADATA",
        "DIVIDEND_011_MISSING_EXTERNAL_CASH_LINK",
        "DIVIDEND_012_MISSING_SETTLEMENT_CASH_ACCOUNT",
        "DIVIDEND_013_NON_POSITIVE_NET_SETTLEMENT",
        "DIVIDEND_014_NEGATIVE_WITHHOLDING_TAX",
        "DIVIDEND_015_WITHHOLDING_EXCEEDS_GROSS_AMOUNT",
    ]


def test_interest_validation_reason_codes_remain_stable() -> None:
    assert [code.value for code in InterestValidationReasonCode] == [
        "INTEREST_001_INVALID_TRANSACTION_TYPE",
        "INTEREST_002_MISSING_SETTLEMENT_DATE",
        "INTEREST_003_NON_ZERO_QUANTITY",
        "INTEREST_004_NON_ZERO_PRICE",
        "INTEREST_005_NON_POSITIVE_GROSS_AMOUNT",
        "INTEREST_006_MISSING_TRADE_CURRENCY",
        "INTEREST_007_MISSING_BOOK_CURRENCY",
        "INTEREST_008_INVALID_DATE_ORDER",
        "INTEREST_009_MISSING_LINKAGE_IDENTIFIER",
        "INTEREST_010_MISSING_POLICY_METADATA",
        "INTEREST_011_MISSING_EXTERNAL_CASH_LINK",
        "INTEREST_012_INVALID_INTEREST_DIRECTION",
        "INTEREST_013_NEGATIVE_WITHHOLDING_TAX",
        "INTEREST_014_NEGATIVE_OTHER_DEDUCTIONS",
        "INTEREST_015_NET_RECONCILIATION_MISMATCH",
        "INTEREST_016_MISSING_SETTLEMENT_CASH_ACCOUNT",
        "INTEREST_017_NON_POSITIVE_NET_SETTLEMENT",
    ]
