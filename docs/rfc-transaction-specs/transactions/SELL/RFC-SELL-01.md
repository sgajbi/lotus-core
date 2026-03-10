# RFC-SELL-01 Canonical SELL Transaction Specification

## 1. Document Metadata

* **Document ID:** RFC-SELL-01
* **Title:** Canonical SELL Transaction Specification
* **Version:** 1.0.0
* **Status:** Draft
* **Owner:** lotus-core engineering
* **Reviewers:** Platform Architecture, lotus-risk engineering
* **Approvers:** lotus-core maintainers
* **Last Updated:** 2026-03-01
* **Effective Date:** 2026-03-01 (pending formal approval)

### 1.1 Change Log

| Version | Date  | Author | Summary                              |
| ------- | ----- | ------ | ------------------------------------ |
| 1.0.0   | 2026-03-01 | lotus-core engineering  | Initial canonical SELL specification |

### 1.2 Purpose

This document defines the canonical, target-state specification for processing a `SELL` transaction in a private-banking / wealth-tech platform.

This RFC is the source of truth for:

* business semantics
* implementation behavior
* AI-assisted code generation
* automated testing
* validation and regression control
* BA analysis
* operations and support runbooks
* reconciliation and audit

Any implementation of `SELL` must conform to this specification unless an approved exception is explicitly documented.

### 1.3 Scope

This RFC applies to all booked `SELL` transactions that reduce or close exposure in financial instruments, including but not limited to:

* equities
* ETFs
* mutual funds
* fixed income / bonds
* money market instruments
* structured products
* other sold securities or positions

This RFC covers:

* input contract
* validation
* enrichment
* policy resolution
* calculation
* position impact
* lot disposal
* cash impact
* accrued-interest handling
* timing semantics
* linkage semantics
* realized P&L decomposition
* query visibility
* observability
* test requirements

### 1.4 Out of Scope

This RFC does not define:

* pre-trade order capture
* pre-trade suitability decisioning
* order routing and execution management
* corporate action transformations
* cancel / correct / rebook flows
* transfer processing not directly linked to the `SELL`
* external settlement messaging workflows beyond required integration fields

Where out-of-scope processes interact with `SELL`, only the required interfaces, identifiers, and linkage expectations are defined here.

---

## 2. Referenced Shared Standards

This RFC must be read together with the shared transaction-processing standards in the repository.

### 2.1 Foundational shared standards

The following shared documents are normative for `SELL` unless explicitly overridden here:

* `shared/01-document-governance.md`
* `shared/02-glossary.md`
* `shared/03-normative-rules-and-precedence.md`
* `shared/04-common-processing-lifecycle.md`
* `shared/05-common-validation-and-failure-semantics.md`
* `shared/06-common-calculation-conventions.md`
* `shared/07-accounting-cash-and-linkage.md`
* `shared/08-timing-semantics.md`
* `shared/09-idempotency-replay-and-reprocessing.md`
* `shared/10-query-audit-and-observability.md`
* `shared/11-test-strategy-and-gap-assessment.md`
* `shared/12-canonical-modeling-guidelines.md`

### 2.2 Override rule

This RFC defines all `SELL`-specific behavior.

If a shared document defines a generic rule and this RFC defines a `SELL`-specific specialization, the `SELL`-specific rule in this RFC takes precedence for `SELL` processing only.

---

## 3. SELL Business Definition

A `SELL` transaction represents the disposal of units of an instrument by a portfolio.

A `SELL` must:

* reduce exposure
* reduce quantity
* dispose of one or more lots
* realize profit or loss based on disposed cost basis and proceeds
* create or link a corresponding cash inflow
* preserve sufficient information for accounting, performance, income, reporting, reconciliation, and audit

A `SELL` must not:

* increase exposure unless explicitly handled as a short-sale transaction type outside this RFC
* be treated as earned income
* dispose more quantity than allowed by the active oversell / shorting policy
* create unlinked cash-side or ledger-side effects

### 3.1 Non-negotiable semantic invariant

A `SELL` disposes exposure, reduces quantity, consumes cost basis, realizes profit or loss, creates settlement cash inflow, and must never be treated as income.

### 3.2 Instrument-neutral rule

The same semantic model must apply across all supported instruments, with policy-driven variations for:

* lot selection
* fee handling
* accrued-interest handling
* timing
* cash-entry mode
* precision and reconciliation behavior

### 3.3 Fixed-income rule

For accrued-interest-bearing instruments:

* accrued interest received on a `SELL` must be captured explicitly
* accrued interest received must not be treated as realized capital P&L
* accrued interest received may be classified separately for income/carry reporting under policy
* proceeds, capital P&L, FX P&L, and accrued-interest components must remain separable

---

## 4. SELL Semantic Invariants

The following invariants are mandatory for every valid `SELL`.

### 4.1 Semantic invariants

* A `SELL` must reduce long exposure.
* A `SELL` must reduce quantity by a positive disposal amount.
* A `SELL` must consume cost basis using the active disposal methodology.
* A `SELL` must realize capital and/or FX P&L, or explicitly realize zero if proceeds equal disposed cost.
* A `SELL` must create settlement cash inflow.
* A `SELL` must consume one or more lots or one average-cost pool slice.
* A `SELL` must not be classified as income.
* A `SELL` must not create new acquisition lots.

### 4.2 Numeric invariants

* `quantity_delta < 0`
* `disposed_quantity > 0`
* `gross_proceeds_local >= 0`
* `dirty_settlement_amount_local >= 0`
* `disposed_cost_basis_local >= 0`
* `disposed_cost_basis_base >= 0`
* `realized_total_pnl = realized_capital_pnl + realized_fx_pnl`

### 4.3 Linkage invariants

* Every `SELL` must have a stable `economic_event_id`.
* Every `SELL` must have a stable `linked_transaction_group_id`.
* If cash is auto-generated, the linked cash entry must exist.
* If cash is upstream-provided, the external cash expectation must be explicit and linkable.
* Security-side and cash-side effects must be reconcilable to the same economic event.

### 4.4 Audit invariants

* Every derived value must be reproducible from source data, linked data, lot state, and policy configuration.
* The active policy id and version must be identifiable for every processed `SELL`.
* Source-system identity and traceability must be preserved.

---

## 5. SELL Processing Flow

The engine must process a `SELL` in the following deterministic sequence.

### 5.1 Receive and ingest

The engine must:

* accept a raw `SELL` payload
* classify it as a `SELL`
* attach source-system metadata
* attach or generate required identifiers
* preserve raw payload lineage where platform policy requires it

### 5.2 Validate

The engine must validate:

* required fields
* field types
* enum values
* signs and ranges
* precision constraints
* policy-required fields
* referential integrity rules
* oversell / shorting rules
* linkage rules
* reconciliation rules for supplied vs derived amounts

Validation outcomes must be explicit and deterministic.

### 5.3 Normalize and enrich

The engine must:

* normalize identifiers
* normalize currencies
* normalize enum values
* derive allowed values when policy permits
* populate policy defaults
* classify fields by source: `UPSTREAM`, `DERIVED`, `CONFIGURED`, `LINKED`, or `STATEFUL`

### 5.4 Resolve policy

The engine must resolve and attach:

* calculation policy id
* calculation policy version
* lot-disposal policy
* fee-treatment policy
* accrued-interest treatment policy
* cash-entry mode
* timing policy
* precision policy
* duplicate/replay policy
* oversell policy

No material calculation may proceed without an active, identifiable policy.

### 5.5 Calculate

The engine must perform calculations in canonical order:

1. determine gross proceeds
2. determine fee buckets
3. determine accrued-interest received
4. determine lot selection / disposal basis
5. determine disposed cost basis
6. determine net proceeds
7. determine realized capital P&L
8. determine realized FX P&L
9. determine total realized P&L
10. convert relevant amounts to base currency
11. determine position deltas
12. determine lot-consumption effects
13. determine cashflow instruction or linked cash expectation

### 5.6 Create business effects

The engine must produce:

* position delta
* lot disposal / reduction
* cashflow effect or linked cash instruction
* realized P&L state
* linkage state
* auditable derived values

### 5.7 Persist and publish

The engine must:

* persist the enriched transaction
* persist derived states
* publish downstream events where applicable
* make the transaction and derived state available to query/read-model consumers according to platform consistency guarantees

### 5.8 Support and traceability

The engine must:

* emit structured logs
* include correlation identifiers
* include economic-event linkage
* expose processing state
* expose failure reason if processing is incomplete

---

## 6. SELL Canonical Data Model

### 6.1 Top-level model

The canonical logical model must be `SellTransaction`.

### 6.2 Required model composition

`SellTransaction` must be composed of:

* `TransactionIdentity`
* `TransactionLifecycle`
* `InstrumentReference`
* `ExecutionDetails`
* `SettlementDetails`
* `QuantityDetails`
* `PriceDetails`
* `ProceedsAmountDetails`
* `FeeDetails`
* `AccruedInterestDetails`
* `FxDetails`
* `ClassificationDetails`
* `PositionEffect`
* `DispositionEffect`
* `RealizedPnlDetails`
* `CashflowInstruction`
* `LinkageDetails`
* `AuditMetadata`
* `AdvisoryMetadata`
* `PolicyMetadata`

### 6.3 Source classification requirement

Each field in the logical model must be classifiable as one of:

* `UPSTREAM`
* `DERIVED`
* `CONFIGURED`
* `LINKED`
* `STATEFUL`

### 6.4 Mutability classification requirement

Each field must have one of the following mutability classifications:

* `IMMUTABLE`
* `DERIVED_ONCE`
* `RECOMPUTED`
* `STATEFUL_BALANCE`

### 6.5 Required field groups and attributes

#### 6.5.1 TransactionIdentity

| Field                         | Type              | Required | Source             | Mutability | Description                                                                   | Sample            |
| ----------------------------- | ----------------- | -------: | ------------------ | ---------- | ----------------------------------------------------------------------------- | ----------------- |
| `transaction_id`              | `str`             |      Yes | UPSTREAM / DERIVED | IMMUTABLE  | Unique identifier of this transaction record                                  | `TXN-2026-000223` |
| `economic_event_id`           | `str`             |      Yes | DERIVED            | IMMUTABLE  | Shared identifier for all linked entries representing the same economic event | `EVT-2026-01987`  |
| `linked_transaction_group_id` | `str`             |      Yes | DERIVED            | IMMUTABLE  | Groups related entries such as the `SELL` and linked cash entry               | `LTG-2026-01456`  |
| `transaction_type`            | `TransactionType` |      Yes | UPSTREAM           | IMMUTABLE  | Canonical transaction type enum                                               | `SELL`            |

#### 6.5.2 TransactionLifecycle

| Field               | Type               | Required | Source                | Mutability | Description                    | Sample                 |
| ------------------- | ------------------ | -------: | --------------------- | ---------- | ------------------------------ | ---------------------- |
| `trade_date`        | `date`             |      Yes | UPSTREAM              | IMMUTABLE  | Trade execution date           | `2026-03-10`           |
| `trade_timestamp`   | `datetime`         |       No | UPSTREAM              | IMMUTABLE  | Exact execution timestamp      | `2026-03-10T11:20:30Z` |
| `settlement_date`   | `date`             |      Yes | UPSTREAM              | IMMUTABLE  | Contractual settlement date    | `2026-03-12`           |
| `booking_date`      | `date \| None`     |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | Accounting booking date        | `2026-03-10`           |
| `value_date`        | `date \| None`     |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | Value date for ledger purposes | `2026-03-12`           |
| `trade_status`      | `TradeStatus`      |      Yes | UPSTREAM / CONFIGURED | RECOMPUTED | Processing state of the trade  | `BOOKED`               |
| `settlement_status` | `SettlementStatus` |      Yes | DERIVED / CONFIGURED  | RECOMPUTED | Settlement lifecycle status    | `PENDING`              |

#### 6.5.3 InstrumentReference

| Field                 | Type                | Required | Source               | Mutability | Description                                                 | Sample         |
| --------------------- | ------------------- | -------: | -------------------- | ---------- | ----------------------------------------------------------- | -------------- |
| `portfolio_id`        | `str`               |      Yes | UPSTREAM             | IMMUTABLE  | Portfolio disposing the instrument                          | `PORT-10001`   |
| `instrument_id`       | `str`               |      Yes | UPSTREAM             | IMMUTABLE  | Canonical instrument identifier                             | `AAPL`         |
| `security_id`         | `str`               |      Yes | UPSTREAM             | IMMUTABLE  | Security master identifier                                  | `US0378331005` |
| `instrument_type`     | `InstrumentType`    |      Yes | UPSTREAM / DERIVED   | IMMUTABLE  | Instrument type used for behavior and reporting             | `EQUITY`       |
| `income_bearing_type` | `IncomeBearingType` |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Whether the instrument accrues income between payment dates | `NON_ACCRUED`  |

#### 6.5.4 ExecutionDetails

| Field             | Type          | Required | Source   | Mutability | Description                              | Sample       |
| ----------------- | ------------- | -------: | -------- | ---------- | ---------------------------------------- | ------------ |
| `execution_venue` | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Venue where the transaction was executed | `NASDAQ`     |
| `broker_id`       | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Executing broker reference               | `BROKER-001` |
| `counterparty_id` | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Counterparty identifier if relevant      | `CP-12345`   |
| `order_id`        | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Upstream order reference                 | `ORD-778900` |
| `fill_id`         | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Execution fill reference                 | `FILL-002`   |

#### 6.5.5 SettlementDetails

| Field                         | Type              | Required | Source                | Mutability | Description                                                | Sample            |
| ----------------------------- | ----------------- | -------: | --------------------- | ---------- | ---------------------------------------------------------- | ----------------- |
| `position_effective_timing`   | `EffectiveTiming` |      Yes | CONFIGURED            | IMMUTABLE  | When the position reduction becomes economically effective | `TRADE_DATE`      |
| `cash_effective_timing`       | `EffectiveTiming` |      Yes | CONFIGURED            | IMMUTABLE  | When cash is increased for ledger purposes                 | `SETTLEMENT_DATE` |
| `performance_cashflow_timing` | `EffectiveTiming` |      Yes | CONFIGURED            | IMMUTABLE  | When performance views recognize the SELL cashflow         | `TRADE_DATE`      |
| `settlement_currency`         | `str`             |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Currency in which settlement occurs                        | `USD`             |
| `cash_account_id`             | `str \| None`     |       No | UPSTREAM              | IMMUTABLE  | Cash account affected by the sale                          | `CASH-USD-01`     |

#### 6.5.6 QuantityDetails

| Field                          | Type      | Required | Source     | Mutability | Description                                                   | Sample |
| ------------------------------ | --------- | -------: | ---------- | ---------- | ------------------------------------------------------------- | ------ |
| `quantity`                     | `Decimal` |      Yes | UPSTREAM   | IMMUTABLE  | Executed sell quantity                                        | `100`  |
| `quantity_precision`           | `int`     |      Yes | CONFIGURED | IMMUTABLE  | Allowed decimal precision for quantity                        | `6`    |
| `settled_quantity_reduction`   | `Decimal` |      Yes | DERIVED    | RECOMPUTED | Quantity reduction already settled at current lifecycle point | `0`    |
| `unsettled_quantity_reduction` | `Decimal` |      Yes | DERIVED    | RECOMPUTED | Quantity reduction pending settlement                         | `100`  |

#### 6.5.7 PriceDetails

| Field             | Type              | Required | Source             | Mutability | Description                                         | Sample     |
| ----------------- | ----------------- | -------: | ------------------ | ---------- | --------------------------------------------------- | ---------- |
| `execution_price` | `Decimal`         |      Yes | UPSTREAM           | IMMUTABLE  | Executed unit sale price                            | `165.00`   |
| `clean_price`     | `Decimal \| None` |       No | UPSTREAM           | IMMUTABLE  | Clean price, primarily for fixed-income instruments | `99.1000`  |
| `dirty_price`     | `Decimal \| None` |       No | UPSTREAM / DERIVED | RECOMPUTED | Dirty price including accrued interest component    | `100.3000` |
| `price_precision` | `int`             |      Yes | CONFIGURED         | IMMUTABLE  | Allowed decimal precision for price                 | `8`        |

#### 6.5.8 ProceedsAmountDetails

| Field                           | Type      | Required | Source             | Mutability   | Description                                                                | Sample     |
| ------------------------------- | --------- | -------: | ------------------ | ------------ | -------------------------------------------------------------------------- | ---------- |
| `gross_proceeds_local`          | `Decimal` |      Yes | UPSTREAM / DERIVED | DERIVED_ONCE | Principal sale amount before fees and before accrued interest separation   | `16500.00` |
| `gross_proceeds_base`           | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Principal sale amount converted to base currency                           | `16500.00` |
| `net_proceeds_local`            | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Sale proceeds after applicable fees, excluding policy-specific separations | `16494.50` |
| `net_proceeds_base`             | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Base-currency equivalent of net proceeds                                   | `16494.50` |
| `dirty_settlement_amount_local` | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Total settlement cash received in trade currency                           | `16494.50` |
| `dirty_settlement_amount_base`  | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Total settlement cash received in base currency                            | `16494.50` |
| `disposed_cost_basis_local`     | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Cost basis consumed by the disposal in trade currency                      | `15005.50` |
| `disposed_cost_basis_base`      | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Cost basis consumed by the disposal in base currency                       | `15005.50` |

#### 6.5.9 FeeDetails

| Field                          | Type      | Required | Source   | Mutability   | Description                                             | Sample |
| ------------------------------ | --------- | -------: | -------- | ------------ | ------------------------------------------------------- | ------ |
| `brokerage_fee_local`          | `Decimal` |      Yes | UPSTREAM | IMMUTABLE    | Brokerage fee in trade currency                         | `5.00` |
| `exchange_fee_local`           | `Decimal` |      Yes | UPSTREAM | IMMUTABLE    | Exchange fee in trade currency                          | `0.50` |
| `stamp_duty_local`             | `Decimal` |      Yes | UPSTREAM | IMMUTABLE    | Stamp duty in trade currency                            | `0.00` |
| `tax_fee_local`                | `Decimal` |      Yes | UPSTREAM | IMMUTABLE    | Tax-related fee in trade currency                       | `0.00` |
| `other_fee_local`              | `Decimal` |      Yes | UPSTREAM | IMMUTABLE    | Other settlement-related fee in trade currency          | `0.00` |
| `proceeds_reducing_fees_local` | `Decimal` |      Yes | DERIVED  | DERIVED_ONCE | Sum of fee components reducing proceeds                 | `5.50` |
| `proceeds_reducing_fees_base`  | `Decimal` |      Yes | DERIVED  | DERIVED_ONCE | Base-currency equivalent of fees reducing proceeds      | `5.50` |
| `expensed_fees_local`          | `Decimal` |      Yes | DERIVED  | DERIVED_ONCE | Sum of fee components expensed separately from proceeds | `0.00` |
| `expensed_fees_base`           | `Decimal` |      Yes | DERIVED  | DERIVED_ONCE | Base-currency equivalent of expensed fees               | `0.00` |

#### 6.5.10 AccruedInterestDetails

| Field                             | Type           | Required | Source             | Mutability   | Description                                            | Sample       |
| --------------------------------- | -------------- | -------: | ------------------ | ------------ | ------------------------------------------------------ | ------------ |
| `accrued_interest_received_local` | `Decimal`      |      Yes | UPSTREAM / DERIVED | DERIVED_ONCE | Accrued interest received from buyer                   | `1200.00`    |
| `accrued_interest_received_base`  | `Decimal`      |      Yes | DERIVED            | DERIVED_ONCE | Base-currency equivalent of accrued interest received  | `1200.00`    |
| `accrued_interest_income_local`   | `Decimal`      |      Yes | DERIVED            | DERIVED_ONCE | Income-classified accrued interest amount under policy | `1200.00`    |
| `accrued_interest_income_base`    | `Decimal`      |      Yes | DERIVED            | DERIVED_ONCE | Base-currency equivalent of accrued interest income    | `1200.00`    |
| `accrual_start_date`              | `date \| None` |       No | UPSTREAM           | IMMUTABLE    | Start date of accrual period                           | `2026-02-15` |
| `accrual_end_date`                | `date \| None` |       No | UPSTREAM           | IMMUTABLE    | End date used to compute accrued interest received     | `2026-03-10` |

#### 6.5.11 FxDetails

| Field                           | Type              | Required | Source                | Mutability | Description                                        | Sample                |
| ------------------------------- | ----------------- | -------: | --------------------- | ---------- | -------------------------------------------------- | --------------------- |
| `trade_currency`                | `str`             |      Yes | UPSTREAM              | IMMUTABLE  | Currency in which the trade is priced              | `USD`                 |
| `portfolio_base_currency`       | `str`             |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Portfolio reporting base currency                  | `USD`                 |
| `trade_fx_rate`                 | `Decimal`         |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | FX rate from trade currency to base currency       | `1.000000`            |
| `settlement_fx_rate`            | `Decimal \| None` |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | FX rate used for settlement currency if different  | `1.000000`            |
| `fx_rate_source`                | `str \| None`     |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | Source of FX rate used                             | `WMR_4PM`             |
| `historical_lot_fx_rate_method` | `str`             |      Yes | CONFIGURED            | IMMUTABLE  | Method used to determine FX impact versus lot cost | `LOT_HISTORICAL_RATE` |

#### 6.5.12 ClassificationDetails

| Field                         | Type                        | Required | Source               | Mutability | Description                                             | Sample                                                    |
| ----------------------------- | --------------------------- | -------: | -------------------- | ---------- | ------------------------------------------------------- | --------------------------------------------------------- |
| `transaction_classification`  | `TransactionClassification` |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | High-level classification of the transaction            | `INVESTMENT`                                              |
| `cashflow_classification`     | `CashflowClassification`    |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Classification of the cash movement                     | `INVESTMENT_INFLOW`                                       |
| `income_classification`       | `IncomeClassification`      |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Income classification applicable to the transaction     | `NONE` or policy-specific accrued-interest classification |
| `realized_pnl_classification` | `RealizedPnlClassification` |      Yes | DERIVED              | IMMUTABLE  | Classification indicating this transaction realizes P&L | `REALIZATION`                                             |

#### 6.5.13 PositionEffect

| Field                     | Type           | Required | Source  | Mutability   | Description                                               | Sample                 |
| ------------------------- | -------------- | -------: | ------- | ------------ | --------------------------------------------------------- | ---------------------- |
| `position_quantity_delta` | `Decimal`      |      Yes | DERIVED | DERIVED_ONCE | Quantity change caused by the `SELL`                      | `-100`                 |
| `cost_basis_delta_local`  | `Decimal`      |      Yes | DERIVED | DERIVED_ONCE | Cost basis reduction in trade currency                    | `-15005.50`            |
| `cost_basis_delta_base`   | `Decimal`      |      Yes | DERIVED | DERIVED_ONCE | Cost basis reduction in base currency                     | `-15005.50`            |
| `held_since_date`         | `date \| None` |      Yes | DERIVED | RECOMPUTED   | Holding-period start date after applying this transaction | `null` if fully closed |

#### 6.5.14 DispositionEffect

| Field                                | Type              | Required | Source     | Mutability   | Description                                       | Sample             |
| ------------------------------------ | ----------------- | -------: | ---------- | ------------ | ------------------------------------------------- | ------------------ |
| `cost_basis_method`                  | `CostBasisMethod` |      Yes | CONFIGURED | IMMUTABLE    | Cost-basis methodology applicable to the disposal | `FIFO`             |
| `disposed_lot_ids`                   | `list[str]`       |      Yes | DERIVED    | DERIVED_ONCE | Identifiers of lots consumed by this `SELL`       | `["LOT-2026-001"]` |
| `disposed_quantity`                  | `Decimal`         |      Yes | DERIVED    | DERIVED_ONCE | Quantity disposed                                 | `100`              |
| `remaining_open_quantity_after_sell` | `Decimal`         |      Yes | DERIVED    | RECOMPUTED   | Remaining open quantity after disposal            | `0`                |

#### 6.5.15 RealizedPnlDetails

| Field                        | Type      | Required | Source  | Mutability   | Description                                                               | Sample    |
| ---------------------------- | --------- | -------: | ------- | ------------ | ------------------------------------------------------------------------- | --------- |
| `realized_capital_pnl_local` | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized capital P&L in trade currency                                    | `1489.00` |
| `realized_fx_pnl_local`      | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized FX P&L in trade currency representation or zero if same-currency | `0.00`    |
| `realized_total_pnl_local`   | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Total realized P&L in trade currency                                      | `1489.00` |
| `realized_capital_pnl_base`  | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized capital P&L in base currency                                     | `1489.00` |
| `realized_fx_pnl_base`       | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized FX P&L in base currency                                          | `0.00`    |
| `realized_total_pnl_base`    | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Total realized P&L in base currency                                       | `1489.00` |

#### 6.5.16 CashflowInstruction

| Field                          | Type            | Required | Source               | Mutability   | Description                                                      | Sample                 |
| ------------------------------ | --------------- | -------: | -------------------- | ------------ | ---------------------------------------------------------------- | ---------------------- |
| `cash_entry_mode`              | `CashEntryMode` |      Yes | CONFIGURED           | IMMUTABLE    | Whether cash entry is engine-generated or expected from upstream | `AUTO_GENERATE`        |
| `auto_generate_cash_entry`     | `bool`          |      Yes | DERIVED / CONFIGURED | IMMUTABLE    | Whether the engine must generate the linked cash entry           | `true`                 |
| `linked_cash_transaction_id`   | `str \| None`   |       No | LINKED / DERIVED     | RECOMPUTED   | Linked cash transaction identifier                               | `TXN-CASH-2026-000223` |
| `settlement_cash_inflow_local` | `Decimal`       |      Yes | DERIVED              | DERIVED_ONCE | Cash added to cash balance in trade currency                     | `16494.50`             |
| `settlement_cash_inflow_base`  | `Decimal`       |      Yes | DERIVED              | DERIVED_ONCE | Cash added to cash balance in base currency                      | `16494.50`             |

#### 6.5.17 LinkageDetails

| Field                        | Type          | Required | Source               | Mutability | Description                                               | Sample             |
| ---------------------------- | ------------- | -------: | -------------------- | ---------- | --------------------------------------------------------- | ------------------ |
| `originating_transaction_id` | `str \| None` |       No | LINKED               | IMMUTABLE  | Source transaction for linked entries                     | `TXN-2026-000223`  |
| `link_type`                  | `LinkType`    |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Semantic meaning of the transaction linkage               | `SECURITY_TO_CASH` |
| `reconciliation_key`         | `str \| None` |       No | UPSTREAM / DERIVED   | IMMUTABLE  | Key used to reconcile with upstream or accounting systems | `RECON-DEF-456`    |

#### 6.5.18 AuditMetadata

| Field                | Type               | Required | Source             | Mutability | Description                             | Sample                 |
| -------------------- | ------------------ | -------: | ------------------ | ---------- | --------------------------------------- | ---------------------- |
| `source_system`      | `str`              |      Yes | UPSTREAM           | IMMUTABLE  | Originating system name                 | `ADVISORY_PLATFORM`    |
| `external_reference` | `str \| None`      |       No | UPSTREAM           | IMMUTABLE  | Upstream external reference             | `EXT-998978`           |
| `booking_center`     | `str \| None`      |       No | UPSTREAM           | IMMUTABLE  | Booking center / legal booking location | `SGPB`                 |
| `created_at`         | `datetime`         |      Yes | UPSTREAM / DERIVED | IMMUTABLE  | Record creation timestamp               | `2026-03-10T11:21:00Z` |
| `processed_at`       | `datetime \| None` |       No | DERIVED            | RECOMPUTED | Processing completion timestamp         | `2026-03-10T11:21:02Z` |

#### 6.5.19 AdvisoryMetadata

| Field                   | Type          | Required | Source   | Mutability | Description                               | Sample           |
| ----------------------- | ------------- | -------: | -------- | ---------- | ----------------------------------------- | ---------------- |
| `advisor_id`            | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Relationship manager / advisor reference  | `RM-1001`        |
| `client_instruction_id` | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Client instruction reference              | `CI-2026-7799`   |
| `suitability_reference` | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Suitability assessment reference          | `SUT-2026-4555`  |
| `mandate_reference`     | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Discretionary or advisory mandate linkage | `DPM-MANDATE-01` |

#### 6.5.20 PolicyMetadata

| Field                               | Type  | Required | Source     | Mutability | Description                                     | Sample                      |
| ----------------------------------- | ----- | -------: | ---------- | ---------- | ----------------------------------------------- | --------------------------- |
| `calculation_policy_id`             | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy identifier used for this calculation     | `POLICY-SELL-STD`           |
| `calculation_policy_version`        | `str` |      Yes | CONFIGURED | IMMUTABLE  | Version of the calculation policy applied       | `1.0.0`                     |
| `lot_disposal_policy`               | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy controlling lot selection and disposal   | `FIFO_DEFAULT`              |
| `accrued_interest_treatment_policy` | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy controlling accrued-interest treatment   | `SEPARATE_FROM_CAPITAL_PNL` |
| `cash_generation_policy`            | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy controlling how cash entries are created | `AUTO_GENERATE_LINKED_CASH` |

---

## 7. SELL Validation Rules

### 7.1 Mandatory required-field validation

A valid `SELL` must include, at minimum:

* transaction identity
* transaction type
* trade date
* settlement date
* portfolio identifier
* instrument identifier
* quantity
* execution price or reconcilable proceeds amount
* trade currency
* portfolio base currency
* applicable FX rate
* required policy identifiers if not resolved externally

### 7.2 Numeric validation

The engine must enforce:

* `quantity > 0`
* `execution_price >= 0`
* `gross_proceeds_local >= 0`
* all fee amounts `>= 0`
* `accrued_interest_received_local >= 0`
* `trade_fx_rate > 0`
* `settlement_fx_rate > 0` when present
* all numeric fields must be decimal-safe
* all numeric fields must satisfy configured precision rules

### 7.3 Reconciliation validation

If both supplied and derived proceeds values are available:

* the engine must reconcile them
* tolerance must be policy-driven
* out-of-tolerance mismatches must fail or park according to policy

### 7.4 Position and disposal validation

The engine must validate, under active oversell policy:

* sufficient position exists for disposal unless oversell/shorting is allowed
* sufficient settled quantity exists if settlement policy requires it
* enough lots or average-cost state exist to support the disposal method
* the disposed quantity can be matched to the configured cost-basis methodology

### 7.5 Enum validation

The engine must validate all enum-constrained fields, including:

* transaction type
* transaction classification
* cashflow classification
* income classification
* timing values
* trade status
* settlement status
* cash-entry mode
* link type
* cost-basis method

### 7.6 Referential validation

The engine must validate, where required:

* portfolio reference exists
* instrument reference exists
* cash account reference exists when explicit account linkage is required
* linked transaction identifiers are valid when separate cash-entry mode is used
* lot references are valid when specific-lot identification is used

### 7.7 Validation outcomes

Each validation failure must resolve to one of:

* `HARD_REJECT`
* `PARK_PENDING_REMEDIATION`
* `ACCEPT_WITH_WARNING`
* `RETRYABLE_FAILURE`
* `TERMINAL_FAILURE`

The applicable outcome must be deterministic and policy-driven.

### 7.8 SELL-specific hard-fail conditions

The following must hard-fail unless explicitly configured otherwise:

* zero quantity
* negative quantity
* missing settlement date
* missing instrument identifier
* missing portfolio identifier
* invalid transaction type
* cross-currency `SELL` with missing required FX rate
* negative accrued interest received
* negative fee component
* policy conflict affecting a material calculation
* oversell not allowed under active policy
* no disposable lots/state available for required disposal method

---

## 8. SELL Calculation Rules and Formulas

### 8.1 Input values

The engine must support calculation from the following normalized inputs:

* quantity
* execution price
* clean price where relevant
* dirty price where relevant
* gross proceeds supplied value where present
* fee components
* accrued interest received
* trade currency
* settlement currency where relevant
* portfolio base currency
* trade FX rate
* settlement FX rate where relevant
* selected lot state / cost-basis state

### 8.2 Derived values

The engine must derive, at minimum:

* `gross_proceeds_local`
* `gross_proceeds_base`
* `proceeds_reducing_fees_local`
* `proceeds_reducing_fees_base`
* `expensed_fees_local`
* `expensed_fees_base`
* `net_proceeds_local`
* `net_proceeds_base`
* `dirty_settlement_amount_local`
* `dirty_settlement_amount_base`
* `accrued_interest_received_base`
* `disposed_cost_basis_local`
* `disposed_cost_basis_base`
* `realized_capital_pnl_local`
* `realized_capital_pnl_base`
* `realized_fx_pnl_local`
* `realized_fx_pnl_base`
* `realized_total_pnl_local`
* `realized_total_pnl_base`
* position deltas
* lot-consumption values
* settlement cash instruction values

### 8.3 Canonical formula order

The engine must calculate in this exact order:

1. determine `gross_proceeds_local`
2. determine fee components and classify them
3. determine `accrued_interest_received_local`
4. determine disposed lots / pool slice
5. determine `disposed_cost_basis_local`
6. determine `net_proceeds_local`
7. determine realized capital P&L
8. determine realized FX P&L
9. determine total realized P&L
10. convert required values into base currency
11. determine position and lot deltas
12. determine linked cash behavior

### 8.4 Gross proceeds calculation

If `gross_proceeds_local` is not explicitly supplied, it must be derived as:

`gross_proceeds_local = quantity × execution_price`

If `gross_proceeds_local` is supplied, it must reconcile with the derived value within configured tolerance.

### 8.5 Fee bucket calculation

The engine must separate fees into:

* proceeds-reducing fees
* separately expensed fees

The classification of each fee component must be policy-driven.

### 8.6 Net proceeds calculation

By default:

`net_proceeds_local = gross_proceeds_local - proceeds_reducing_fees_local`

If policy separates accrued interest from sale proceeds, net proceeds for capital realization must exclude accrued interest.

### 8.7 Dirty settlement amount calculation

By default:

`dirty_settlement_amount_local = net_proceeds_local + accrued_interest_received_local`

if accrued interest is received as part of settlement cash and treated separately from capital proceeds.

If policy folds accrued interest into the same cash component, the total must still remain decomposable for reporting.

### 8.8 Disposed cost-basis calculation

The engine must determine disposed cost basis using the active `cost_basis_method`.

Examples:

* FIFO: consume oldest eligible lots first
* AVCO: apply average cost per unit × disposed quantity
* Specific lot: consume explicitly referenced lots

### 8.9 Realized capital P&L calculation

By default:

`realized_capital_pnl_local = net_proceeds_local - disposed_cost_basis_local`

If accrued interest is separated from capital proceeds, it must not inflate capital P&L.

### 8.10 Realized FX P&L calculation

The engine must compute FX realization separately from capital realization when applicable.

The method must be policy-driven and auditable. At minimum it must support:

* same-currency disposal resulting in `0`
* cross-currency disposal using historical lot/base cost context versus current realization amount

### 8.11 Total realized P&L calculation

`realized_total_pnl = realized_capital_pnl + realized_fx_pnl`

This must hold in both local and base representations, subject to configured representation rules.

### 8.12 Base-currency conversion

The engine must convert all relevant local amounts to base currency using the active FX policy.

By default:

`amount_base = amount_local × applicable_fx_rate`

The FX source, precision, and rounding behavior must be policy-driven and traceable.

### 8.13 Rounding and precision

The engine must define:

* internal calculation precision
* rounding scale per amount type
* rounding mode
* presentation scale
* FX conversion rounding rules
* reconciliation tolerance rules

Rounding must be applied only at defined calculation boundaries and must not vary by implementation.

---

## 9. SELL Position Rules

### 9.1 Quantity effect

A `SELL` must reduce position quantity by the executed quantity.

`new_quantity = old_quantity - quantity`

### 9.2 Position reduction rule

If the pre-transaction position quantity is positive and remains positive after the `SELL`, the position remains open with reduced quantity.

### 9.3 Position close rule

If the `SELL` reduces the position quantity to zero, the position is fully closed.

### 9.4 Settled vs unsettled quantity

The engine must support both:

* settled quantity reduction
* unsettled quantity reduction

Behavior must depend on `position_effective_timing` and settlement lifecycle state.

### 9.5 Cost-basis effect

A `SELL` must reduce position cost basis by:

* `disposed_cost_basis_local`
* `disposed_cost_basis_base`

These deltas must be negative on the position.

### 9.6 Held-since behavior

* If the position remains open after the `SELL`, `held_since_date` must remain unchanged.
* If the `SELL` fully closes the position, `held_since_date` becomes null / absent until a future re-open.
* A `SELL` must not create a new holding period.

### 9.7 Position rule invariants

* Position quantity must decrease.
* Cost basis must decrease by the defined disposed cost-basis amount.
* A `SELL` must realize P&L according to the disposal rule.
* A `SELL` must not increase quantity unless handled by a different approved shorting flow.

---

## 10. SELL Lot Rules

### 10.1 Lot disposal

Every valid `SELL` must consume one or more lots or a defined average-cost pool slice.

### 10.2 Required lot-disposal behavior

Each disposal effect must contain:

* disposed lot identifiers
* source transaction reference
* disposal date
* disposed quantity
* consumed lot cost local
* consumed lot cost base
* any remaining open quantity
* accrued-interest state where relevant
* FX context
* policy context

### 10.3 Lot quantity reduction

For each consumed lot:

* `lot_open_quantity_after = lot_open_quantity_before - disposed_quantity_from_that_lot`

No lot may go negative unless explicitly allowed by a policy outside this RFC.

### 10.4 Lot cost consumption

The engine must consume cost from lots using the active disposal methodology.

### 10.5 Fixed-income treatment

For fixed-income disposals:

* accrued interest received must be stored separately from principal disposal
* lot consumption must remain separable from accrued-interest settlement components

### 10.6 Methodology compatibility

The lot-disposal model must support:

* FIFO
* average-cost pooling
* specific-lot identification

### 10.7 Lot traceability

Every lot disposal must remain traceable to:

* source transaction id
* economic event id
* policy id and version

---

## 11. SELL Cash and Dual-Accounting Rules

### 11.1 Core cash rule

A `SELL` must increase cash.

### 11.2 Required cash concepts

The engine must support:

* capital proceeds
* settlement cash amount

These amounts may differ depending on accrued-interest and fee policy.

### 11.3 Settlement cash rule

By default:

`settlement_cash_inflow_local = dirty_settlement_amount_local`

`settlement_cash_inflow_base = dirty_settlement_amount_base`

### 11.4 Cash-entry modes

The system must support both:

* `AUTO_GENERATE`
* `UPSTREAM_PROVIDED`

### 11.5 Auto-generated cash mode

If `cash_entry_mode = AUTO_GENERATE`:

* the engine must create a linked cash entry
* the linked cash entry must increase cash balance
* the entry must be linked to the originating `SELL`

### 11.6 Upstream-provided cash mode

If `cash_entry_mode = UPSTREAM_PROVIDED`:

* the engine must not generate a duplicate cash entry
* the engine must accept a separate upstream cash transaction
* the engine must link that cash transaction to the `SELL`

### 11.7 Required linkage fields

Security-side and cash-side entries must be linkable through:

* `economic_event_id`
* `linked_transaction_group_id`
* `originating_transaction_id`
* `linked_cash_transaction_id`
* `link_type`
* `reconciliation_key` where applicable

### 11.8 Cash balance views

The platform must distinguish, where relevant:

* available cash
* settled cash
* projected cash
* ledger cash

### 11.9 Cash invariants

* A `SELL` cash effect must always be linked or explicitly externally expected.
* Duplicate cash creation must be prevented.
* Cash-side and security-side effects must reconcile to the same economic event.

---

## 12. SELL Accrued-Interest Rules

### 12.1 Core rule

Accrued interest received on a `SELL` must not be treated as realized capital P&L.

### 12.2 Required storage

The engine must store:

* accrued interest received local
* accrued interest received base
* any income-classified accrued-interest component required by policy

### 12.3 Fixed-income proceeds separation

For accrued-interest-bearing instruments, the engine must separate:

* principal sale proceeds
* accrued interest received
* fees
* realized capital P&L
* realized FX P&L

### 12.4 Income interaction

If policy classifies accrued interest received as income/carry:

* it must be visible distinctly from capital realization
* it must not distort realized capital P&L
* it must remain auditable and traceable to the `SELL`

### 12.5 Accrued-interest invariants

* Accrued interest received must be explicit if present.
* Accrued interest must never be merged indistinguishably into capital P&L.
* The treatment must be policy-driven, explicit, and reportable.

---

## 13. SELL Timing Rules

### 13.1 Timing dimensions

The engine must support these timing dimensions independently:

* position timing
* cash timing
* performance timing
* reporting timing

### 13.2 Supported timing values

Supported values must include:

* `TRADE_DATE`
* `SETTLEMENT_DATE`

### 13.3 Trade-date economic effect

If position timing is `TRADE_DATE`:

* exposure reduction becomes economically visible on trade date
* quantity may be reflected as unsettled reduction until settlement

### 13.4 Settlement-date legal effect

If settlement timing is `SETTLEMENT_DATE`:

* legal settlement occurs on settlement date
* unsettled quantity reduction transitions to settled reduction on settlement date
* cash is increased for settlement-ledger purposes on settlement date unless configured otherwise

### 13.5 Cash timing

If cash timing is `TRADE_DATE`:

* cash may be recognized as receivable / projected on trade date

If cash timing is `SETTLEMENT_DATE`:

* actual ledger cash movement occurs on settlement date

### 13.6 Performance timing

The system must support performance recognition under the configured performance timing policy.

### 13.7 Timing invariants

* Timing behavior must be policy-driven, explicit, and auditable.
* Different timing modes must not produce silent inconsistencies between position, cash, P&L, and reporting views.

---

## 14. SELL Query / Output Contract

### 14.1 Required query surfaces

After successful processing, the platform must expose:

* enriched transaction view
* position view
* lot-disposal view
* cash linkage view
* realized-P&L view
* audit view

### 14.2 Required transaction output fields

At minimum, downstream consumers must be able to retrieve:

* canonical transaction identifiers
* core business fields
* derived proceeds fields
* classification fields
* timing fields
* policy metadata
* explicit realized P&L structure
* linkage fields

### 14.3 Required position output fields

At minimum:

* quantity
* settled quantity
* unsettled quantity
* cost basis local
* cost basis base
* held-since date (or null if closed)

### 14.4 Required lot-disposal output fields

At minimum:

* disposed lot ids
* disposal date
* disposed quantity
* remaining open quantity
* consumed cost
* accrued-interest separation where relevant
* policy and FX context

### 14.5 Required realized-P&L output fields

At minimum:

* realized capital P&L local/base
* realized FX P&L local/base
* realized total P&L local/base

### 14.6 Consistency expectation

The platform must define whether these surfaces are:

* synchronous
* eventually consistent

and must document the expected latency/SLA for visibility.

---

## 15. SELL Worked Examples

### 15.1 Example A: Same-currency equity SELL

#### Inputs

* instrument type: `EQUITY`
* quantity: `100`
* execution price: `165.00`
* gross proceeds supplied: not supplied
* brokerage fee: `5.00`
* exchange fee: `0.50`
* other fees: `0.00`
* accrued interest received: `0.00`
* trade currency: `USD`
* portfolio base currency: `USD`
* trade FX rate: `1.000000`
* cash entry mode: `AUTO_GENERATE`
* cost-basis method: `FIFO`
* disposed lot cost basis local: `15005.50`

#### Derivations

* `gross_proceeds_local = 100 × 165.00 = 16500.00`
* `proceeds_reducing_fees_local = 5.00 + 0.50 = 5.50`
* `net_proceeds_local = 16500.00 - 5.50 = 16494.50`
* `dirty_settlement_amount_local = 16494.50 + 0.00 = 16494.50`
* `disposed_cost_basis_local = 15005.50`
* `realized_capital_pnl_local = 16494.50 - 15005.50 = 1489.00`
* `realized_fx_pnl_local = 0.00`
* `realized_total_pnl_local = 1489.00`
* same values in base currency

#### Expected outputs

* position quantity decreases by `100`
* cost basis decreases by `15005.50`
* one lot is fully consumed
* linked cash entry is auto-generated for `16494.50`
* `held_since_date = null` if fully closed

#### Invariants checked

* negative quantity delta
* realized capital P&L correctly computed
* realized FX P&L zero in same-currency case
* not classified as income

---

### 15.2 Example B: Cross-currency equity SELL

#### Inputs

* instrument type: `EQUITY`
* quantity: `100`
* execution price: `165.00`
* fees total local: `5.50`
* accrued interest received: `0.00`
* trade currency: `USD`
* portfolio base currency: `SGD`
* trade FX rate: `1.350000`
* disposed cost basis base uses historical lot context under policy

#### Derivations

* `gross_proceeds_local = 16500.00`
* `net_proceeds_local = 16494.50`
* `dirty_settlement_amount_local = 16494.50`
* `gross_proceeds_base = 22275.00`
* `net_proceeds_base = 22267.575`
* disposed cost basis base determined from historical lot/base state
* realized capital P&L base and realized FX P&L base computed separately under policy

#### Expected outputs

* position quantity decreases by `100`
* local and base realized P&L are both populated
* realized FX P&L is explicit and traceable
* cash effect remains linked and traceable

---

### 15.3 Example C: Bond SELL with accrued interest

#### Inputs

* instrument type: `BOND`
* quantity: `100`
* clean-price-derived gross proceeds local: `99100.00`
* proceeds-reducing fees local: `40.00`
* accrued interest received local: `1200.00`
* trade currency: `USD`
* base currency: `USD`
* trade FX rate: `1.000000`
* disposed cost basis local: `98040.00`
* accrued-interest policy: `SEPARATE_FROM_CAPITAL_PNL`

#### Derivations

* `net_proceeds_local = 99100.00 - 40.00 = 99060.00`
* `dirty_settlement_amount_local = 99060.00 + 1200.00 = 100260.00`
* `disposed_cost_basis_local = 98040.00`
* `realized_capital_pnl_local = 99060.00 - 98040.00 = 1020.00`
* `accrued_interest_received_local = 1200.00`
* `realized_fx_pnl_local = 0.00`
* `realized_total_pnl_local = 1020.00`

#### Expected outputs

* position cost basis decreases by `98040.00`
* lot is consumed according to disposal policy
* settlement cash inflow reflects `100260.00`
* accrued interest is stored separately from capital realization

#### Invariants checked

* accrued interest is not treated as capital P&L
* settlement cash may exceed net capital proceeds
* realized capital P&L remains separable

---

### 15.4 Example D: Partial SELL with remaining position

#### Inputs

* pre-transaction position quantity: `300`
* sell quantity: `100`

#### Expected outputs

* new position quantity: `200`
* position remains open
* `held_since_date` remains unchanged
* only the disposed lots / quantities are reduced
* remaining lots stay open with updated quantities

---

### 15.5 Example E: Auto-generated cash entry

#### Inputs

* `cash_entry_mode = AUTO_GENERATE`

#### Required outcome

* the engine generates a linked cash entry
* the cash entry has the same `economic_event_id`
* `originating_transaction_id` links back to the `SELL`
* no duplicate cash entry may be produced on replay

---

### 15.6 Example F: Upstream-provided cash entry

#### Inputs

* `cash_entry_mode = UPSTREAM_PROVIDED`

#### Required outcome

* the engine does not auto-generate a duplicate cash entry
* the external cash transaction is accepted and linked
* security-side and cash-side effects remain reconcilable

---

## 16. SELL Decision Tables

### 16.1 Instrument-type decision table

| Condition                                                            | Required behavior                                  |
| -------------------------------------------------------------------- | -------------------------------------------------- |
| Equity / non-accrual instrument                                      | No accrued-interest separation required            |
| Fixed-income / accrual-bearing instrument with accrued interest      | Separate accrued interest from capital realization |
| Fixed-income / accrual-bearing instrument with zero accrued interest | Accrued-interest component remains zero            |

### 16.2 Accrued-interest treatment decision table

| Condition                                              | Capital proceeds               | Settlement cash                           | Income visibility                           |
| ------------------------------------------------------ | ------------------------------ | ----------------------------------------- | ------------------------------------------- |
| Policy separates accrued interest                      | Excludes accrued interest      | Includes accrued interest                 | Separate accrued-interest reporting allowed |
| Policy folds accrued interest into same cash component | Still must remain decomposable | Includes accrued interest                 | Must still remain separately reportable     |
| No accrued interest present                            | No separation needed           | Equals net proceeds subject to other fees | None                                        |

### 16.3 Cash-entry mode decision table

| Condition                | Required behavior                                                              |
| ------------------------ | ------------------------------------------------------------------------------ |
| `AUTO_GENERATE`          | Engine generates linked cash entry                                             |
| `UPSTREAM_PROVIDED`      | Engine expects and links external cash entry                                   |
| Linked cash arrives late | Security-side record remains traceable and pending reconciliation until linked |

### 16.4 Timing decision table

| Condition                                     | Required behavior                                          |
| --------------------------------------------- | ---------------------------------------------------------- |
| `position_effective_timing = TRADE_DATE`      | Position reduces economically on trade date                |
| `position_effective_timing = SETTLEMENT_DATE` | Position reduces on settlement date                        |
| `cash_effective_timing = TRADE_DATE`          | Cash may be recognized as receivable on trade date         |
| `cash_effective_timing = SETTLEMENT_DATE`     | Cash is increased for ledger settlement on settlement date |

### 16.5 Lot-disposal decision table

| Condition               | Required behavior                                   |
| ----------------------- | --------------------------------------------------- |
| `FIFO`                  | Dispose oldest eligible lots first                  |
| `AVCO`                  | Dispose pooled average-cost slice                   |
| No valid disposal state | Fail or park according to disposal validation rules |

---

## 17. SELL Test Matrix

The implementation is not complete unless the following test categories are covered.

### 17.1 Validation tests

* accept valid standard `SELL`
* reject zero quantity
* reject negative quantity
* reject negative fee component
* reject negative accrued interest received
* reject missing settlement date
* reject missing required FX for cross-currency `SELL`
* reject invalid enum values
* reject proceeds mismatch beyond tolerance
* reject policy conflicts
* reject oversell when not allowed
* reject invalid specific-lot references

### 17.2 Calculation tests

* same-currency equity `SELL`
* cross-currency equity `SELL`
* equity `SELL` with multiple fee components
* equity `SELL` with proceeds-reducing and expensed fee split
* bond `SELL` with accrued interest
* cross-currency bond `SELL` with accrued interest
* accrued interest separated from capital P&L
* accrued interest folded into a single cash component but still decomposed
* separate realized capital and FX P&L calculation

### 17.3 Position tests

* `SELL` reducing but not closing a position
* `SELL` fully closing a position
* trade-date-effective position reduction
* settlement-date-effective position reduction
* settled/unsettled quantity transition
* held-since unchanged on partial sell
* held-since null after full close

### 17.4 Lot tests

* lot disposal for every `SELL`
* correct disposed quantity
* correct remaining open quantity
* correct consumed cost basis
* FIFO disposal
* average-cost disposal
* specific-lot disposal
* fixed-income disposal with accrued-interest separation

### 17.5 Cash and dual-accounting tests

* auto-generated linked cash entry
* upstream-provided linked cash entry
* duplicate cash prevention
* linkage integrity
* same-currency settlement cash
* cross-currency settlement cash
* trade-date cash effect
* settlement-date cash effect

### 17.6 Realized P&L tests

* realized capital P&L same-currency
* realized FX P&L zero same-currency
* cross-currency realized FX P&L explicit
* total realized P&L equals capital + FX
* zero-gain/zero-loss case still explicit

### 17.7 Query tests

* enriched transaction visibility
* position visibility after partial `SELL`
* position visibility after full close
* lot-disposal visibility
* cash linkage visibility
* realized-P&L visibility
* policy metadata visibility

### 17.8 Idempotency and replay tests

* same transaction replay does not duplicate business effects
* duplicate `SELL` detection
* duplicate linked cash prevention
* replay-safe regeneration of derived state
* late-arriving linked cash reconciles correctly

### 17.9 Failure-mode tests

* validation hard-fail
* park pending remediation
* retryable processing failure
* terminal processing failure
* partial processing with explicit state visibility

---

## 18. SELL Edge Cases and Failure Cases

### 18.1 Edge cases

The engine must explicitly handle:

* zero quantity
* negative quantity
* zero execution price
* missing settlement date
* cross-currency `SELL` without required FX
* supplied proceeds mismatching quantity × price
* zero accrued interest on accrual-bearing instrument
* multiple fee components with mixed treatment
* `SELL` partially reducing a position
* `SELL` fully closing a position
* `SELL` with late linked cash entry
* `SELL` replay / duplicate arrival
* disposal touching multiple lots
* zero total realized P&L despite valid disposal

### 18.2 Failure cases

The engine must explicitly define behavior for:

* validation failure
* referential integrity failure
* policy-resolution failure
* reconciliation failure
* duplicate detection conflict
* linked cash missing beyond expected SLA
* event publish failure after local persistence
* query-read-model lag or partial propagation
* oversell blocked by policy
* missing lot state for required disposal method

### 18.3 Failure semantics requirement

For each failure class, the system must define:

* status
* reason code
* whether retriable
* whether blocking
* whether user-visible
* what operational action is required

---

## 19. SELL Configurable Policies

All material `SELL` behavior must be configurable through versioned policy, not code forks.

### 19.1 Mandatory configurable dimensions

The following must be configurable:

* proceeds supplied vs derived
* quantity precision
* price precision
* FX precision
* reconciliation tolerance
* fee treatment by fee component
* accrued-interest treatment
* whether accrued interest is included in settlement cash
* whether accrued interest is emitted as a separate linked cash component
* cash-entry mode
* position timing
* cash timing
* performance timing
* lot-disposal method
* linkage enforcement
* duplicate/replay handling
* tax handling as fee vs separate charge
* oversell / shorting behavior
* settlement-eligibility rules

### 19.2 Policy traceability

Every processed `SELL` must preserve:

* `calculation_policy_id`
* `calculation_policy_version`

### 19.3 Policy conflict rule

If two policies or policy fragments conflict in a way that changes a material outcome, the engine must not silently choose one. It must fail or park according to policy-resolution rules.

---

## 20. SELL Gap Assessment Checklist

This section defines the required template for assessing the current implementation against this RFC.

For each requirement, implementation review must record:

* requirement id or title
* current implementation status:

  * `COVERED`
  * `PARTIALLY_COVERED`
  * `NOT_COVERED`
* behavior match status:

  * `MATCHES`
  * `PARTIALLY_MATCHES`
  * `DOES_NOT_MATCH`
* current observed behavior
* target required behavior
* risk if unchanged
* proposed action
* blocking / non-blocking
* tests required
* schema impact
* behavior-change impact

### 20.1 Characterization rule

If the current implementation already matches a requirement in this RFC, that behavior must be locked with characterization tests before refactoring or enhancement.

### 20.2 Completion rule

`SELL` is complete only when:

* the full input contract is implemented
* all mandatory validations are enforced
* all mandatory calculations are implemented
* lot-disposal support is implemented
* dual-accounting support is implemented
* realized capital and FX P&L decomposition is implemented
* timing behavior is implemented
* all required metadata is preserved
* all required query outputs are available
* invariants are enforced
* the required test matrix is complete
* all remaining gaps are explicitly documented and approved

---

## 21. Appendices

### Appendix A: Error and Reason Codes

The platform must maintain a supporting catalog for:

* validation errors
* reconciliation mismatches
* policy-resolution failures
* linkage failures
* duplicate/replay conflicts
* disposal failures
* processing failures

### Appendix B: Configuration Reference

The platform must maintain a supporting catalog for each configurable policy item, including:

* config name
* type
* allowed values
* default
* effect
* whether the setting has historical recalculation impact

### Appendix C: Field Catalog Extensions

Additional institution-specific fields may be added only if they:

* do not violate this RFC
* are documented in the field catalog
* preserve source classification and mutability metadata
* remain auditable and testable

### Appendix D: Future Transaction RFC Alignment

Subsequent transaction RFCs (such as `DIVIDEND`, `INTEREST`, `TRANSFER_IN`) must follow the same structural pattern as this `SELL` RFC to ensure consistency across:

* engineering implementation
* AI-assisted coding
* QA and regression
* BA analysis
* support and ops runbooks
* audit and reconciliation

---

## 22. Final Authoritative Statement

This RFC is the canonical specification for `SELL`.

If an implementation, test, support workflow, or downstream consumer behavior conflicts with this document, this document is the source of truth unless an approved exception or superseding RFC version explicitly states otherwise.
