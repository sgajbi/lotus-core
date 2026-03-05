# DIVIDEND Slice 1 Validation Reason Codes

This document defines the initial DIVIDEND validation reason-code catalog introduced in Slice 1.

| Code | Field | Meaning |
|---|---|---|
| `DIVIDEND_001_INVALID_TRANSACTION_TYPE` | `transaction_type` | Payload is not DIVIDEND while being validated under DIVIDEND canonical rules. |
| `DIVIDEND_002_MISSING_SETTLEMENT_DATE` | `settlement_date` | Settlement date is mandatory for canonical DIVIDEND validation. |
| `DIVIDEND_003_NON_ZERO_QUANTITY` | `quantity` | DIVIDEND quantity must be exactly zero. |
| `DIVIDEND_004_NON_ZERO_PRICE` | `price` | DIVIDEND price must be exactly zero. |
| `DIVIDEND_005_NON_POSITIVE_GROSS_AMOUNT` | `gross_transaction_amount` | Gross dividend amount must be strictly greater than zero. |
| `DIVIDEND_006_MISSING_TRADE_CURRENCY` | `trade_currency` | Trade currency is required. |
| `DIVIDEND_007_MISSING_BOOK_CURRENCY` | `currency` | Booked currency is required. |
| `DIVIDEND_008_INVALID_DATE_ORDER` | `transaction_date` | Booking date must not be after settlement date. |
| `DIVIDEND_009_MISSING_LINKAGE_IDENTIFIER` | `economic_event_id` | Strict mode requires linkage identifiers. |
| `DIVIDEND_010_MISSING_POLICY_METADATA` | `calculation_policy_id` | Strict mode requires policy id and version. |

## Notes

- Slice 1 introduces this catalog and validator foundation.
- Runtime strict enforcement in live ingestion flow is staged for later slices.
- Strict mode is currently available through domain validator invocation (`strict_metadata=True`).
