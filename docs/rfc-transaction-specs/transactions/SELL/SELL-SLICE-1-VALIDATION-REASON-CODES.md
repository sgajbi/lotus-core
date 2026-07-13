# SELL Slice 1 Validation Reason Codes

This document defines the initial SELL validation reason-code catalog introduced in Slice 1.

| Code | Field | Meaning |
|---|---|---|
| `SELL_001_INVALID_TRANSACTION_TYPE` | `transaction_type` | Payload is not SELL while being validated under SELL canonical rules. |
| `SELL_002_MISSING_SETTLEMENT_DATE` | `settlement_date` | Settlement date is mandatory for canonical SELL validation. |
| `SELL_003_NON_POSITIVE_QUANTITY` | `quantity` | SELL quantity must be strictly greater than zero. |
| `SELL_004_NON_POSITIVE_GROSS_AMOUNT` | `gross_transaction_amount` | Gross proceeds amount must be strictly greater than zero. |
| `SELL_005_MISSING_TRADE_CURRENCY` | `trade_currency` | Trade currency is required. |
| `SELL_006_MISSING_BOOK_CURRENCY` | `currency` | Booked currency is required. |
| `SELL_007_INVALID_DATE_ORDER` | `transaction_date` | Trade date must not be after settlement date. |
| `SELL_008_MISSING_LINKAGE_IDENTIFIER` | `economic_event_id` | Strict mode requires linkage identifiers. |
| `SELL_009_MISSING_POLICY_METADATA` | `calculation_policy_id` | Strict mode requires policy id and version. |
| `SELL_010_NON_POSITIVE_NET_SETTLEMENT` | `trade_fee` | Resolved transaction fees leave zero or negative settlement proceeds. |

## Notes

- Slice 1 introduces this catalog and validator foundation.
- Runtime processing rejects `SELL_010_NON_POSITIVE_NET_SETTLEMENT` before financial writes.
- Strict mode is currently available through domain validator invocation (`strict_metadata=True`).
