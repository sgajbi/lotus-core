# INTEREST Slice 1 - Validation and Reason Codes

## Scope

Slice 1 establishes canonical INTEREST validation foundation:

- canonical INTEREST model
- deterministic INTEREST reason-code taxonomy
- INTEREST validator with strict metadata mode
- unit coverage aligned to BUY/SELL/DIVIDEND patterns

No runtime processing behavior is changed in this slice.

## Delivered Artifacts

- `src/services/portfolio_transaction_processing_service/app/domain/transaction/booked.py`
- `src/services/portfolio_transaction_processing_service/app/domain/transaction/validation/reason_codes.py`
- `src/services/portfolio_transaction_processing_service/app/domain/transaction/validation/income.py`
- `src/services/portfolio_transaction_processing_service/app/domain/transaction/__init__.py` (exports)
- `tests/unit/services/portfolio_transaction_processing_service/domain/transaction/validation/test_income.py`

## Reason Code Taxonomy

Implemented reason codes:

- `INTEREST_001_INVALID_TRANSACTION_TYPE`
- `INTEREST_002_MISSING_SETTLEMENT_DATE`
- `INTEREST_003_NON_ZERO_QUANTITY`
- `INTEREST_004_NON_ZERO_PRICE`
- `INTEREST_005_NON_POSITIVE_GROSS_AMOUNT`
- `INTEREST_006_MISSING_TRADE_CURRENCY`
- `INTEREST_007_MISSING_BOOK_CURRENCY`
- `INTEREST_008_INVALID_DATE_ORDER`
- `INTEREST_009_MISSING_LINKAGE_IDENTIFIER`
- `INTEREST_010_MISSING_POLICY_METADATA`
- `INTEREST_011_MISSING_EXTERNAL_CASH_LINK`
- `INTEREST_012_INVALID_INTEREST_DIRECTION`
- `INTEREST_013_NEGATIVE_WITHHOLDING_TAX`
- `INTEREST_014_NEGATIVE_OTHER_DEDUCTIONS`
- `INTEREST_015_NET_RECONCILIATION_MISMATCH`
- `INTEREST_016_MISSING_SETTLEMENT_CASH_ACCOUNT`
- `INTEREST_017_NON_POSITIVE_NET_SETTLEMENT`

## Validation Behavior

`validate_interest_transaction` enforces:

- `transaction_type` must be `INTEREST`
- `settlement_date` required
- `quantity == 0`
- `price == 0`
- `gross_transaction_amount > 0`
- required currencies present
- transaction date must not be after settlement date
- strict metadata mode requires linkage and policy metadata
- `cash_entry_mode=UPSTREAM_PROVIDED` requires `external_cash_transaction_id`
- `cash_entry_mode=AUTO_GENERATE` requires `settlement_cash_account_id`
- interest direction, deduction signs, and explicit pre-fee net interest reconcile deterministically
- income settlement must remain strictly positive after resolved transaction fees

`INTEREST_015_NET_RECONCILIATION_MISMATCH` and
`INTEREST_017_NON_POSITIVE_NET_SETTLEMENT` are non-retryable runtime rejections performed after
idempotency classification and before financial writes. A mismatched explicit net is not trusted as
settlement evidence, and non-positive income settlement is not repaired by applying an
absolute-value inflow sign.

## Shared-Doc Conformance Note (Slice 1)

Validated shared standards for this slice:

- `shared/05-common-validation-and-failure-semantics.md`: deterministic reason-code driven validation implemented.
- `shared/07-accounting-cash-and-linkage.md`: external cash-link requirement enforced in validator.
- `shared/11-test-strategy-and-gap-assessment.md`: unit tests added for happy path and failure taxonomy.
- `shared/12-canonical-modeling-guidelines.md`: canonical transaction model added with explicit field semantics.

## Residual Gaps (Expected for Later Slices)

- Metadata enrichment and policy defaulting are Slice 2.
- INTEREST calculation invariants and direction semantics are Slice 3.
- cash-entry mode execution behavior is Slice 4.
- query/observability surfaces are Slice 5.

