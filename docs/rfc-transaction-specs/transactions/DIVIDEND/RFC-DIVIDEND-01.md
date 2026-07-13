# RFC-DIVIDEND-01 Canonical DIVIDEND Transaction Specification

## 1. Document Metadata

* **Document ID:** RFC-DIVIDEND-01
* **Title:** Canonical DIVIDEND Transaction Specification
* **Version:** 1.0.0
* **Status:** Draft
* **Owner:** *TBD*
* **Reviewers:** *TBD*
* **Approvers:** *TBD*
* **Last Updated:** *TBD*
* **Effective Date:** *TBD*

### 1.1 Change Log

| Version | Date  | Author | Summary                                  |
| ------- | ----- | ------ | ---------------------------------------- |
| 1.0.0   | *TBD* | *TBD*  | Initial canonical DIVIDEND specification |

### 1.2 Purpose

This document defines the canonical, target-state specification for processing a `DIVIDEND` transaction in a private-banking / wealth-tech platform.

This RFC is the source of truth for:

* business semantics
* implementation behavior
* AI-assisted code generation
* automated testing
* validation and regression control
* BA analysis
* operations and support runbooks
* reconciliation and audit

Any implementation of `DIVIDEND` must conform to this specification unless an approved exception is explicitly documented.

### 1.3 Scope

This RFC applies to all booked `DIVIDEND` transactions that represent distribution of cash income from a held instrument, including but not limited to:

* equity cash dividends
* ETF cash distributions
* fund cash distributions
* REIT distributions
* return-of-capital-like cash distributions when classified under dividend workflows by policy
* withholding-tax-adjusted dividend receipts
* gross and net dividend representations

This RFC covers:

* input contract
* validation
* enrichment
* policy resolution
* calculation
* income recognition
* withholding-tax handling
* cost-basis impact where applicable by policy
* cash impact
* timing semantics
* linkage semantics
* query visibility
* observability
* test requirements

### 1.4 Out of Scope

This RFC does not define:

* stock dividends / bonus shares / scrip dividends that create quantity changes
* coupon / bond interest flows
* corporate action transformations outside cash dividend booking
* cancel / correct / rebook flows
* reclaim workflows beyond required linkage fields
* external settlement messaging workflows beyond required integration fields

Where out-of-scope processes interact with `DIVIDEND`, only the required interfaces, identifiers, and linkage expectations are defined here.

---

## 2. Referenced Shared Standards

This RFC must be read together with the shared transaction-processing standards in the repository.

### 2.1 Foundational shared standards

The following shared documents are normative for `DIVIDEND` unless explicitly overridden here:

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

This RFC defines all `DIVIDEND`-specific behavior.

If a shared document defines a generic rule and this RFC defines a `DIVIDEND`-specific specialization, the `DIVIDEND`-specific rule in this RFC takes precedence for `DIVIDEND` processing only.

---

## 3. DIVIDEND Business Definition

A `DIVIDEND` transaction represents a cash income distribution received by a portfolio from a held instrument.

A `DIVIDEND` must:

* recognize income
* optionally recognize withholding tax
* create or link a corresponding cash inflow
* preserve gross vs net income visibility
* preserve sufficient information for accounting, tax, reporting, reconciliation, and audit

A `DIVIDEND` must not:

* change instrument quantity
* create or consume acquisition lots
* create realized capital P&L
* create realized FX P&L
* be treated as a buy/sell disposal event
* silently merge withholding tax into net cash without preserving gross visibility

### 3.1 Non-negotiable semantic invariant

A `DIVIDEND` recognizes income, may recognize withholding tax, creates settlement cash inflow, and must not change quantity, cost basis, or realized capital/FX P&L unless explicitly classified as return-of-capital under policy.

### 3.2 Instrument-neutral rule

The same semantic model must apply across all supported income-distributing instruments, with policy-driven variations for:

* gross vs net receipt representation
* withholding-tax treatment
* return-of-capital handling
* timing
* cash-entry mode
* precision and reconciliation behavior

### 3.3 Return-of-capital rule

If a distribution is classified as return of capital under active policy:

* the return-of-capital component must be explicitly separated from ordinary dividend income
* the return-of-capital component may reduce cost basis under policy
* the ordinary income component and cost-basis-reducing component must remain separately reportable and auditable

---

## 4. DIVIDEND Semantic Invariants

The following invariants are mandatory for every valid `DIVIDEND`.

### 4.1 Semantic invariants

* A `DIVIDEND` must not change quantity.
* A `DIVIDEND` must not create or consume lots.
* A `DIVIDEND` must recognize gross income, net income, or both according to policy.
* A `DIVIDEND` must create settlement cash inflow or explicit linked external cash expectation.
* A `DIVIDEND` must preserve withholding-tax visibility if tax applies.
* A `DIVIDEND` must not create realized capital P&L.
* A `DIVIDEND` must not create realized FX P&L.
* A `DIVIDEND` must not be classified as an investment buy/sell flow.

### 4.2 Numeric invariants

* `quantity_delta = 0`
* `gross_dividend_local >= 0`
* `gross_dividend_base >= 0`
* `withholding_tax_local >= 0`
* `withholding_tax_base >= 0`
* `net_dividend_local >= 0`
* `net_dividend_base >= 0`
* settlement cash after resolved transaction fees must be strictly greater than zero
* `net_dividend = gross_dividend - withholding_tax - other_receipt_deductions`
* realized capital P&L local = `0`
* realized FX P&L local = `0`
* realized total P&L local = `0`
* realized capital P&L base = `0`
* realized FX P&L base = `0`
* realized total P&L base = `0`

### 4.3 Linkage invariants

* Every `DIVIDEND` must have a stable `economic_event_id`.
* Every `DIVIDEND` must have a stable `linked_transaction_group_id`.
* If cash is auto-generated, the linked cash entry must exist.
* If cash is upstream-provided, the external cash expectation must be explicit and linkable.
* Income-side and cash-side effects must be reconcilable to the same economic event.

### 4.4 Audit invariants

* Every derived value must be reproducible from source data, linked data, position context if relevant, and policy configuration.
* The active policy id and version must be identifiable for every processed `DIVIDEND`.
* Source-system identity and traceability must be preserved.

---

## 5. DIVIDEND Processing Flow

The engine must process a `DIVIDEND` in the following deterministic sequence.

### 5.1 Receive and ingest

The engine must:

* accept a raw `DIVIDEND` payload
* classify it as a `DIVIDEND`
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
* gross/net income policy
* withholding-tax treatment policy
* return-of-capital policy
* cash-entry mode
* timing policy
* precision policy
* duplicate/replay policy

No material calculation may proceed without an active, identifiable policy.

### 5.5 Calculate

The engine must perform calculations in canonical order:

1. determine gross dividend
2. determine withholding tax
3. determine other receipt deductions
4. determine return-of-capital component if applicable
5. determine ordinary income component
6. determine net dividend cash
7. convert relevant amounts to base currency
8. determine cost-basis effect if return-of-capital applies
9. emit explicit zero realized P&L values
10. determine cashflow instruction or linked cash expectation

### 5.6 Create business effects

The engine must produce:

* income recognition effect
* tax effect
* cost-basis adjustment effect if applicable by policy
* cashflow effect or linked cash instruction
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

## 6. DIVIDEND Canonical Data Model

### 6.1 Top-level model

The canonical logical model must be `DividendTransaction`.

### 6.2 Required model composition

`DividendTransaction` must be composed of:

* `TransactionIdentity`
* `TransactionLifecycle`
* `InstrumentReference`
* `IncomeEventDetails`
* `SettlementDetails`
* `AmountDetails`
* `TaxDetails`
* `ReturnOfCapitalDetails`
* `FxDetails`
* `ClassificationDetails`
* `PositionEffect`
* `IncomeEffect`
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
| `transaction_id`              | `str`             |      Yes | UPSTREAM / DERIVED | IMMUTABLE  | Unique identifier of this transaction record                                  | `TXN-2026-000323` |
| `economic_event_id`           | `str`             |      Yes | DERIVED            | IMMUTABLE  | Shared identifier for all linked entries representing the same economic event | `EVT-2026-02987`  |
| `linked_transaction_group_id` | `str`             |      Yes | DERIVED            | IMMUTABLE  | Groups related entries such as the `DIVIDEND` and linked cash entry           | `LTG-2026-02456`  |
| `transaction_type`            | `TransactionType` |      Yes | UPSTREAM           | IMMUTABLE  | Canonical transaction type enum                                               | `DIVIDEND`        |

#### 6.5.2 TransactionLifecycle

| Field               | Type               | Required | Source                | Mutability | Description                            | Sample       |
| ------------------- | ------------------ | -------: | --------------------- | ---------- | -------------------------------------- | ------------ |
| `declaration_date`  | `date \| None`     |       No | UPSTREAM              | IMMUTABLE  | Date the dividend was declared         | `2026-03-01` |
| `ex_date`           | `date \| None`     |       No | UPSTREAM              | IMMUTABLE  | Ex-dividend date                       | `2026-03-10` |
| `record_date`       | `date \| None`     |       No | UPSTREAM              | IMMUTABLE  | Record date for entitlement            | `2026-03-12` |
| `payment_date`      | `date`             |      Yes | UPSTREAM              | IMMUTABLE  | Contractual payment date               | `2026-03-20` |
| `booking_date`      | `date \| None`     |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | Accounting booking date                | `2026-03-20` |
| `value_date`        | `date \| None`     |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | Value date for ledger purposes         | `2026-03-20` |
| `income_status`     | `IncomeStatus`     |      Yes | UPSTREAM / CONFIGURED | RECOMPUTED | Processing state of the dividend event | `BOOKED`     |
| `settlement_status` | `SettlementStatus` |      Yes | DERIVED / CONFIGURED  | RECOMPUTED | Settlement lifecycle status            | `PENDING`    |

#### 6.5.3 InstrumentReference

| Field               | Type              | Required | Source             | Mutability | Description                                     | Sample         |
| ------------------- | ----------------- | -------: | ------------------ | ---------- | ----------------------------------------------- | -------------- |
| `portfolio_id`      | `str`             |      Yes | UPSTREAM           | IMMUTABLE  | Portfolio receiving the dividend                | `PORT-10001`   |
| `instrument_id`     | `str`             |      Yes | UPSTREAM           | IMMUTABLE  | Canonical instrument identifier                 | `AAPL`         |
| `security_id`       | `str`             |      Yes | UPSTREAM           | IMMUTABLE  | Security master identifier                      | `US0378331005` |
| `instrument_type`   | `InstrumentType`  |      Yes | UPSTREAM / DERIVED | IMMUTABLE  | Instrument type used for behavior and reporting | `EQUITY`       |
| `entitled_quantity` | `Decimal \| None` |       No | UPSTREAM / DERIVED | IMMUTABLE  | Quantity used for entitlement/reconciliation    | `100`          |

#### 6.5.4 IncomeEventDetails

| Field                        | Type                | Required | Source                | Mutability | Description                                         | Sample          |
| ---------------------------- | ------------------- | -------: | --------------------- | ---------- | --------------------------------------------------- | --------------- |
| `dividend_type`              | `DividendType`      |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Type of dividend/distribution                       | `CASH_ORDINARY` |
| `income_rate_per_unit_local` | `Decimal \| None`   |       No | UPSTREAM              | IMMUTABLE  | Dividend amount per entitled unit in local currency | `0.82`          |
| `gross_or_net_indicator`     | `GrossNetIndicator` |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Whether upstream amount is gross or net             | `GROSS`         |
| `withholding_tax_applicable` | `bool`              |      Yes | DERIVED / CONFIGURED  | IMMUTABLE  | Whether withholding tax applies                     | `true`          |

#### 6.5.5 SettlementDetails

| Field                         | Type              | Required | Source                | Mutability | Description                                            | Sample         |
| ----------------------------- | ----------------- | -------: | --------------------- | ---------- | ------------------------------------------------------ | -------------- |
| `cash_effective_timing`       | `EffectiveTiming` |      Yes | CONFIGURED            | IMMUTABLE  | When cash is increased for ledger purposes             | `PAYMENT_DATE` |
| `income_effective_timing`     | `EffectiveTiming` |      Yes | CONFIGURED            | IMMUTABLE  | When income is recognized                              | `PAYMENT_DATE` |
| `performance_cashflow_timing` | `EffectiveTiming` |      Yes | CONFIGURED            | IMMUTABLE  | When performance views recognize the dividend cashflow | `PAYMENT_DATE` |
| `settlement_currency`         | `str`             |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Currency in which cash is received                     | `USD`          |
| `cash_account_id`             | `str \| None`     |       No | UPSTREAM              | IMMUTABLE  | Cash account affected by the dividend receipt          | `CASH-USD-01`  |

#### 6.5.6 AmountDetails

| Field                            | Type      | Required | Source             | Mutability   | Description                                  | Sample  |
| -------------------------------- | --------- | -------: | ------------------ | ------------ | -------------------------------------------- | ------- |
| `gross_dividend_local`           | `Decimal` |      Yes | UPSTREAM / DERIVED | DERIVED_ONCE | Gross dividend amount before tax             | `82.00` |
| `gross_dividend_base`            | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Base-currency equivalent of gross dividend   | `82.00` |
| `other_receipt_deductions_local` | `Decimal` |      Yes | UPSTREAM / DERIVED | DERIVED_ONCE | Other deductions reducing cash receipt       | `0.00`  |
| `other_receipt_deductions_base`  | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Base-currency equivalent of other deductions | `0.00`  |
| `net_dividend_local`             | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Net cash dividend received                   | `69.70` |
| `net_dividend_base`              | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Base-currency equivalent of net dividend     | `69.70` |
| `settlement_cash_inflow_local`   | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Cash added to cash balance in local currency | `69.70` |
| `settlement_cash_inflow_base`    | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Cash added to cash balance in base currency  | `69.70` |

#### 6.5.7 TaxDetails

| Field                        | Type              | Required | Source             | Mutability   | Description                                     | Sample  |
| ---------------------------- | ----------------- | -------: | ------------------ | ------------ | ----------------------------------------------- | ------- |
| `withholding_tax_local`      | `Decimal`         |      Yes | UPSTREAM / DERIVED | DERIVED_ONCE | Tax withheld from the gross dividend            | `12.30` |
| `withholding_tax_base`       | `Decimal`         |      Yes | DERIVED            | DERIVED_ONCE | Base-currency equivalent of withholding tax     | `12.30` |
| `withholding_tax_rate`       | `Decimal \| None` |       No | UPSTREAM / DERIVED | DERIVED_ONCE | Applied withholding-tax rate                    | `0.15`  |
| `tax_reclaim_eligible_local` | `Decimal \| None` |       No | DERIVED            | DERIVED_ONCE | Portion potentially reclaimable under policy    | `0.00`  |
| `tax_reclaim_eligible_base`  | `Decimal \| None` |       No | DERIVED            | DERIVED_ONCE | Base-currency equivalent of reclaimable portion | `0.00`  |

#### 6.5.8 ReturnOfCapitalDetails

| Field                        | Type      | Required | Source  | Mutability   | Description                                                 | Sample |
| ---------------------------- | --------- | -------: | ------- | ------------ | ----------------------------------------------------------- | ------ |
| `return_of_capital_local`    | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Portion of the distribution classified as return of capital | `0.00` |
| `return_of_capital_base`     | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Base-currency equivalent of return of capital               | `0.00` |
| `cost_basis_reduction_local` | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Cost-basis reduction triggered by return of capital         | `0.00` |
| `cost_basis_reduction_base`  | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Base-currency equivalent of cost-basis reduction            | `0.00` |

#### 6.5.9 FxDetails

| Field                     | Type              | Required | Source                | Mutability | Description                                       | Sample     |
| ------------------------- | ----------------- | -------: | --------------------- | ---------- | ------------------------------------------------- | ---------- |
| `income_currency`         | `str`             |      Yes | UPSTREAM              | IMMUTABLE  | Currency in which the dividend is declared        | `USD`      |
| `portfolio_base_currency` | `str`             |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Portfolio reporting base currency                 | `USD`      |
| `income_fx_rate`          | `Decimal`         |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | FX rate from income currency to base currency     | `1.000000` |
| `settlement_fx_rate`      | `Decimal \| None` |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | FX rate used for settlement currency if different | `1.000000` |
| `fx_rate_source`          | `str \| None`     |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | Source of FX rate used                            | `WMR_4PM`  |

#### 6.5.10 ClassificationDetails

| Field                        | Type                        | Required | Source               | Mutability | Description                                         | Sample            |
| ---------------------------- | --------------------------- | -------: | -------------------- | ---------- | --------------------------------------------------- | ----------------- |
| `transaction_classification` | `TransactionClassification` |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | High-level classification of the transaction        | `INCOME`          |
| `cashflow_classification`    | `CashflowClassification`    |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Classification of the cash movement                 | `INCOME_INFLOW`   |
| `income_classification`      | `IncomeClassification`      |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Income classification applicable to the transaction | `DIVIDEND`        |
| `tax_classification`         | `TaxClassification`         |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Tax classification of the withheld amount           | `WITHHOLDING_TAX` |

#### 6.5.11 PositionEffect

| Field                     | Type      | Required | Source  | Mutability   | Description                              | Sample |
| ------------------------- | --------- | -------: | ------- | ------------ | ---------------------------------------- | ------ |
| `position_quantity_delta` | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Quantity change caused by the `DIVIDEND` | `0`    |
| `cost_basis_delta_local`  | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Cost-basis change in local currency      | `0.00` |
| `cost_basis_delta_base`   | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Cost-basis change in base currency       | `0.00` |

#### 6.5.12 IncomeEffect

| Field                   | Type      | Required | Source  | Mutability   | Description                                 | Sample  |
| ----------------------- | --------- | -------: | ------- | ------------ | ------------------------------------------- | ------- |
| `ordinary_income_local` | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Ordinary dividend income recognized         | `82.00` |
| `ordinary_income_base`  | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Base-currency equivalent of ordinary income | `82.00` |
| `net_income_local`      | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Net income after withholding and deductions | `69.70` |
| `net_income_base`       | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Base-currency equivalent of net income      | `69.70` |

#### 6.5.13 RealizedPnlDetails

| Field                        | Type      | Required | Source  | Mutability   | Description                            | Sample |
| ---------------------------- | --------- | -------: | ------- | ------------ | -------------------------------------- | ------ |
| `realized_capital_pnl_local` | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized capital P&L in local currency | `0.00` |
| `realized_fx_pnl_local`      | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized FX P&L in local currency      | `0.00` |
| `realized_total_pnl_local`   | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Total realized P&L in local currency   | `0.00` |
| `realized_capital_pnl_base`  | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized capital P&L in base currency  | `0.00` |
| `realized_fx_pnl_base`       | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized FX P&L in base currency       | `0.00` |
| `realized_total_pnl_base`    | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Total realized P&L in base currency    | `0.00` |

#### 6.5.14 CashflowInstruction

| Field                          | Type            | Required | Source               | Mutability   | Description                                                      | Sample                 |
| ------------------------------ | --------------- | -------: | -------------------- | ------------ | ---------------------------------------------------------------- | ---------------------- |
| `cash_entry_mode`              | `CashEntryMode` |      Yes | CONFIGURED           | IMMUTABLE    | Whether cash entry is engine-generated or expected from upstream | `AUTO_GENERATE`        |
| `auto_generate_cash_entry`     | `bool`          |      Yes | DERIVED / CONFIGURED | IMMUTABLE    | Whether the engine must generate the linked cash entry           | `true`                 |
| `linked_cash_transaction_id`   | `str \| None`   |       No | LINKED / DERIVED     | RECOMPUTED   | Linked cash transaction identifier                               | `TXN-CASH-2026-000323` |
| `settlement_cash_inflow_local` | `Decimal`       |      Yes | DERIVED              | DERIVED_ONCE | Cash added to cash balance in local currency                     | `69.70`                |
| `settlement_cash_inflow_base`  | `Decimal`       |      Yes | DERIVED              | DERIVED_ONCE | Cash added to cash balance in base currency                      | `69.70`                |

#### 6.5.15 LinkageDetails

| Field                        | Type          | Required | Source               | Mutability | Description                                               | Sample            |
| ---------------------------- | ------------- | -------: | -------------------- | ---------- | --------------------------------------------------------- | ----------------- |
| `originating_transaction_id` | `str \| None` |       No | LINKED               | IMMUTABLE  | Source transaction for linked entries                     | `TXN-2026-000323` |
| `link_type`                  | `LinkType`    |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Semantic meaning of the transaction linkage               | `INCOME_TO_CASH`  |
| `reconciliation_key`         | `str \| None` |       No | UPSTREAM / DERIVED   | IMMUTABLE  | Key used to reconcile with upstream or accounting systems | `RECON-GHI-789`   |

#### 6.5.16 AuditMetadata

| Field                | Type               | Required | Source             | Mutability | Description                             | Sample                  |
| -------------------- | ------------------ | -------: | ------------------ | ---------- | --------------------------------------- | ----------------------- |
| `source_system`      | `str`              |      Yes | UPSTREAM           | IMMUTABLE  | Originating system name                 | `CORP_ACTIONS_PLATFORM` |
| `external_reference` | `str \| None`      |       No | UPSTREAM           | IMMUTABLE  | Upstream external reference             | `EXT-999111`            |
| `booking_center`     | `str \| None`      |       No | UPSTREAM           | IMMUTABLE  | Booking center / legal booking location | `SGPB`                  |
| `created_at`         | `datetime`         |      Yes | UPSTREAM / DERIVED | IMMUTABLE  | Record creation timestamp               | `2026-03-20T09:00:00Z`  |
| `processed_at`       | `datetime \| None` |       No | DERIVED            | RECOMPUTED | Processing completion timestamp         | `2026-03-20T09:00:02Z`  |

#### 6.5.17 AdvisoryMetadata

| Field                   | Type          | Required | Source   | Mutability | Description                                     | Sample           |
| ----------------------- | ------------- | -------: | -------- | ---------- | ----------------------------------------------- | ---------------- |
| `advisor_id`            | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Relationship manager / advisor reference        | `RM-1001`        |
| `client_instruction_id` | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Client instruction reference if manually booked | `CI-2026-7801`   |
| `mandate_reference`     | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Mandate linkage if relevant                     | `DPM-MANDATE-01` |

#### 6.5.18 PolicyMetadata

| Field                        | Type  | Required | Source     | Mutability | Description                                     | Sample                                      |
| ---------------------------- | ----- | -------: | ---------- | ---------- | ----------------------------------------------- | ------------------------------------------- |
| `calculation_policy_id`      | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy identifier used for this calculation     | `POLICY-DIV-STD`                            |
| `calculation_policy_version` | `str` |      Yes | CONFIGURED | IMMUTABLE  | Version of the calculation policy applied       | `1.0.0`                                     |
| `withholding_tax_policy`     | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy controlling withholding-tax treatment    | `PRESERVE_GROSS_AND_NET`                    |
| `return_of_capital_policy`   | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy controlling ROC treatment                | `SEPARATE_AND_REDUCE_COST_BASIS_IF_PRESENT` |
| `cash_generation_policy`     | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy controlling how cash entries are created | `AUTO_GENERATE_LINKED_CASH`                 |

---

## 7. DIVIDEND Validation Rules

### 7.1 Mandatory required-field validation

A valid `DIVIDEND` must include, at minimum:

* transaction identity
* transaction type
* payment date
* portfolio identifier
* instrument identifier
* gross amount or reconcilable per-unit/rate-based amount
* income currency
* portfolio base currency
* applicable FX rate
* required policy identifiers if not resolved externally

### 7.2 Numeric validation

The engine must enforce:

* `gross_dividend_local >= 0`
* `withholding_tax_local >= 0`
* `other_receipt_deductions_local >= 0`
* `return_of_capital_local >= 0`
* `income_fx_rate > 0`
* `settlement_fx_rate > 0` when present
* all numeric fields must be decimal-safe
* all numeric fields must satisfy configured precision rules

### 7.3 Reconciliation validation

If both supplied total amount and derived per-unit × entitled-quantity values are available:

* the engine must reconcile them
* tolerance must be policy-driven
* out-of-tolerance mismatches must fail or park according to policy

### 7.4 Entitlement validation

Where policy requires entitlement validation, the engine must validate:

* that the portfolio was entitled based on ex/record date logic or upstream entitlement confirmation
* that entitled quantity is present or derivable where required
* that the income event maps to a valid held instrument or upstream exception rule

### 7.5 Enum validation

The engine must validate all enum-constrained fields, including:

* transaction type
* transaction classification
* cashflow classification
* income classification
* timing values
* income status
* settlement status
* cash-entry mode
* link type
* dividend type

### 7.6 Referential validation

The engine must validate, where required:

* portfolio reference exists
* instrument reference exists
* cash account reference exists when explicit account linkage is required
* linked transaction identifiers are valid when separate cash-entry mode is used

### 7.7 Validation outcomes

Each validation failure must resolve to one of:

* `HARD_REJECT`
* `PARK_PENDING_REMEDIATION`
* `ACCEPT_WITH_WARNING`
* `RETRYABLE_FAILURE`
* `TERMINAL_FAILURE`

The applicable outcome must be deterministic and policy-driven.

### 7.8 DIVIDEND-specific hard-fail conditions

The following must hard-fail unless explicitly configured otherwise:

* negative gross dividend
* missing payment date
* missing instrument identifier
* missing portfolio identifier
* invalid transaction type
* cross-currency dividend with missing required FX rate
* negative withholding tax
* negative return-of-capital amount
* policy conflict affecting a material calculation

---

## 8. DIVIDEND Calculation Rules and Formulas

### 8.1 Input values

The engine must support calculation from the following normalized inputs:

* gross dividend supplied value where present
* per-unit dividend rate where present
* entitled quantity where present
* withholding tax amount or rate
* other receipt deductions
* return-of-capital component where present
* income currency
* settlement currency where relevant
* portfolio base currency
* income FX rate
* settlement FX rate where relevant

### 8.2 Derived values

The engine must derive, at minimum:

* `gross_dividend_local`
* `gross_dividend_base`
* `withholding_tax_local`
* `withholding_tax_base`
* `other_receipt_deductions_local`
* `other_receipt_deductions_base`
* `ordinary_income_local`
* `ordinary_income_base`
* `return_of_capital_local`
* `return_of_capital_base`
* `cost_basis_reduction_local`
* `cost_basis_reduction_base`
* `net_dividend_local`
* `net_dividend_base`
* `settlement_cash_inflow_local`
* `settlement_cash_inflow_base`
* explicit realized P&L zero values

### 8.3 Canonical formula order

The engine must calculate in this exact order:

1. determine `gross_dividend_local`
2. determine `withholding_tax_local`
3. determine `other_receipt_deductions_local`
4. determine `return_of_capital_local`
5. determine `ordinary_income_local`
6. determine `net_dividend_local`
7. convert required values into base currency
8. determine cost-basis reduction if return of capital applies
9. emit explicit zero realized P&L fields
10. determine linked cash behavior

### 8.4 Gross dividend calculation

If `gross_dividend_local` is not explicitly supplied and rate data is available, it may be derived as:

`gross_dividend_local = income_rate_per_unit_local × entitled_quantity`

If `gross_dividend_local` is supplied, it must reconcile with the derived value within configured tolerance where both are available.

### 8.5 Withholding tax calculation

If withholding tax is supplied as a rate:

`withholding_tax_local = gross_dividend_local × withholding_tax_rate`

If withholding tax is supplied as an amount, it must reconcile to any rate-derived value within configured tolerance where both are available.

### 8.6 Ordinary income calculation

By default:

`ordinary_income_local = gross_dividend_local - return_of_capital_local`

If no return-of-capital component exists:

`ordinary_income_local = gross_dividend_local`

### 8.7 Net dividend calculation

By default:

`net_dividend_local = gross_dividend_local - withholding_tax_local - other_receipt_deductions_local`

If policy requires return-of-capital separation, the net cash amount may still include ROC, but income reporting must remain decomposed.

### 8.8 Settlement cash calculation

By default:

`settlement_cash_inflow_local = net_dividend_local`

If policy represents tax or deductions as separate linked ledger entries, the total economic event must still reconcile to gross less deductions.

### 8.9 Cost-basis reduction calculation

If a return-of-capital component is present and policy requires basis reduction:

`cost_basis_reduction_local = return_of_capital_local`

Otherwise:

`cost_basis_reduction_local = 0`

### 8.10 Base-currency conversion

The engine must convert all relevant local amounts to base currency using the active FX policy.

By default:

`amount_base = amount_local × applicable_fx_rate`

The FX source, precision, and rounding behavior must be policy-driven and traceable.

### 8.11 Realized P&L fields

For every `DIVIDEND`, the engine must explicitly produce:

* realized capital P&L local = `0`
* realized FX P&L local = `0`
* realized total P&L local = `0`
* realized capital P&L base = `0`
* realized FX P&L base = `0`
* realized total P&L base = `0`

These fields must be present and must not be omitted.

### 8.12 Rounding and precision

The engine must define:

* internal calculation precision
* rounding scale per amount type
* rounding mode
* presentation scale
* FX conversion rounding rules
* reconciliation tolerance rules

Rounding must be applied only at defined calculation boundaries and must not vary by implementation.

---

## 9. DIVIDEND Position Rules

### 9.1 Quantity effect

A `DIVIDEND` must not change position quantity.

`new_quantity = old_quantity`

### 9.2 Cost-basis effect

By default, a `DIVIDEND` must not change cost basis.

If a return-of-capital component exists under active policy:

* cost basis may be reduced by `cost_basis_reduction_local`
* the reduction must be explicit and separately reportable from ordinary income

### 9.3 Held-since behavior

A `DIVIDEND` must not change `held_since_date`.

### 9.4 Position rule invariants

* Position quantity must remain unchanged.
* No lots may be created or consumed.
* Cost basis must remain unchanged unless return-of-capital policy explicitly reduces it.

---

## 10. DIVIDEND Cash and Dual-Accounting Rules

### 10.1 Core cash rule

A `DIVIDEND` must increase cash.

### 10.2 Required cash concepts

The engine must support:

* gross income amount
* tax deductions
* net settlement cash amount

### 10.3 Settlement cash rule

By default:

`settlement_cash_inflow_local = net_dividend_local`

`settlement_cash_inflow_base = net_dividend_base`

### 10.4 Cash-entry modes

The system must support both:

* `AUTO_GENERATE`
* `UPSTREAM_PROVIDED`

### 10.5 Auto-generated cash mode

If `cash_entry_mode = AUTO_GENERATE`:

* the engine must create a linked cash entry
* the linked cash entry must increase cash balance
* the entry must be linked to the originating `DIVIDEND`

### 10.6 Upstream-provided cash mode

If `cash_entry_mode = UPSTREAM_PROVIDED`:

* the engine must not generate a duplicate cash entry
* the engine must accept a separate upstream cash transaction
* the engine must link that cash transaction to the `DIVIDEND`

### 10.7 Required linkage fields

Income-side and cash-side entries must be linkable through:

* `economic_event_id`
* `linked_transaction_group_id`
* `originating_transaction_id`
* `linked_cash_transaction_id`
* `link_type`
* `reconciliation_key` where applicable

### 10.8 Cash balance views

The platform must distinguish, where relevant:

* available cash
* settled cash
* projected cash
* ledger cash

### 10.9 Cash invariants

* A `DIVIDEND` cash effect must always be linked or explicitly externally expected.
* Duplicate cash creation must be prevented.
* Cash-side and income-side effects must reconcile to the same economic event.

---

## 11. DIVIDEND Tax and Return-of-Capital Rules

### 11.1 Withholding-tax rule

If withholding tax applies:

* gross dividend must remain visible
* withholding tax must remain visible
* net cash received must remain visible

The engine must not preserve only net cash and discard gross/tax decomposition.

### 11.2 Tax reporting rule

Withholding tax must be separately classifiable and reportable for:

* tax reporting
* statement reporting
* reclaim workflows where relevant

### 11.3 Return-of-capital rule

If a portion of the distribution is return of capital:

* it must be explicitly separated from ordinary income
* it must be explicitly separated from withholding tax
* it may reduce cost basis under policy
* it must remain auditable

### 11.4 Tax and ROC invariants

* Withholding tax must never be merged indistinguishably into net cash.
* Return of capital must never be merged indistinguishably into ordinary income.
* Tax and ROC treatment must be policy-driven, explicit, and reportable.

---

## 12. DIVIDEND Timing Rules

### 12.1 Timing dimensions

The engine must support these timing dimensions independently:

* income recognition timing
* cash timing
* performance timing
* reporting timing

### 12.2 Supported timing values

Supported values must include:

* `EX_DATE`
* `RECORD_DATE`
* `PAYMENT_DATE`
* `BOOKING_DATE`

### 12.3 Income recognition timing

The system must support income recognition under the configured policy, typically on:

* payment date, or
* record date, where institution policy requires accrual-style recognition

### 12.4 Cash timing

Cash is typically realized on payment date, but the system must support policy-driven variants.

### 12.5 Performance timing

The system must support performance recognition under the configured performance timing policy.

### 12.6 Timing invariants

* Timing behavior must be policy-driven, explicit, and auditable.
* Different timing modes must not silently distort income, cash, and reporting views.

---

## 13. DIVIDEND Query / Output Contract

### 13.1 Required query surfaces

After successful processing, the platform must expose:

* enriched transaction view
* income view
* cash linkage view
* tax view
* cost-basis adjustment view where ROC applies
* audit view

### 13.2 Required transaction output fields

At minimum, downstream consumers must be able to retrieve:

* canonical transaction identifiers
* core business fields
* gross/net/tax decomposition
* classification fields
* timing fields
* policy metadata
* explicit realized P&L structure
* linkage fields

### 13.3 Required income output fields

At minimum:

* ordinary income local/base
* net income local/base
* withholding tax local/base
* return of capital local/base

### 13.4 Required position output fields

At minimum:

* unchanged quantity
* cost-basis change if any
* no lot creation/consumption indicator

### 13.5 Consistency expectation

The platform must define whether these surfaces are:

* synchronous
* eventually consistent

and must document the expected latency/SLA for visibility.

---

## 14. DIVIDEND Worked Examples

### 14.1 Example A: Ordinary cash dividend with withholding tax

#### Inputs

* instrument type: `EQUITY`
* entitled quantity: `100`
* rate per unit: `0.82`
* gross dividend supplied: not supplied
* withholding tax rate: `0.15`
* other deductions: `0.00`
* return of capital: `0.00`
* income currency: `USD`
* portfolio base currency: `USD`
* income FX rate: `1.000000`
* cash entry mode: `AUTO_GENERATE`

#### Derivations

* `gross_dividend_local = 0.82 × 100 = 82.00`
* `withholding_tax_local = 82.00 × 0.15 = 12.30`
* `ordinary_income_local = 82.00`
* `net_dividend_local = 82.00 - 12.30 - 0.00 = 69.70`
* `settlement_cash_inflow_local = 69.70`
* base equivalents are identical
* realized P&L fields = `0.00`

#### Expected outputs

* no quantity change
* no lot activity
* linked cash entry for `69.70`
* withholding tax stored separately
* ordinary income recorded as `82.00`

#### Invariants checked

* gross, tax, and net all visible
* no realized capital P&L
* not classified as investment buy/sell

---

### 14.2 Example B: Gross amount supplied directly

#### Inputs

* gross dividend supplied: `125.00`
* withholding tax supplied: `18.75`
* other deductions: `0.00`

#### Derivations

* `ordinary_income_local = 125.00`
* `net_dividend_local = 125.00 - 18.75 = 106.25`
* `settlement_cash_inflow_local = 106.25`

#### Expected outputs

* gross and net remain separately visible
* withholding tax remains separately visible
* no quantity change

---

### 14.3 Example C: Return-of-capital distribution

#### Inputs

* gross dividend local: `100.00`
* return of capital local: `30.00`
* withholding tax local: `0.00`

#### Derivations

* `ordinary_income_local = 100.00 - 30.00 = 70.00`
* `return_of_capital_local = 30.00`
* `cost_basis_reduction_local = 30.00`
* `net_dividend_local = 100.00`

#### Expected outputs

* cash inflow = `100.00`
* ordinary income = `70.00`
* return of capital = `30.00`
* cost basis reduced by `30.00`

#### Invariants checked

* ROC is not merged into ordinary income
* cost-basis reduction is explicit and auditable

---

### 14.4 Example D: Cross-currency dividend

#### Inputs

* gross dividend local: `82.00 USD`
* withholding tax local: `12.30 USD`
* income FX rate: `1.350000`
* base currency: `SGD`

#### Derivations

* `gross_dividend_base = 82.00 × 1.35 = 110.70`
* `withholding_tax_base = 12.30 × 1.35 = 16.605`
* `net_dividend_base = 69.70 × 1.35 = 94.095`

#### Expected outputs

* local and base income amounts populated
* no realized FX P&L
* FX conversion remains explicit and traceable

---

### 14.5 Example E: Auto-generated cash entry

#### Inputs

* `cash_entry_mode = AUTO_GENERATE`

#### Required outcome

* the engine generates a linked cash entry
* the cash entry has the same `economic_event_id`
* `originating_transaction_id` links back to the `DIVIDEND`
* no duplicate cash entry may be produced on replay

---

### 14.6 Example F: Upstream-provided cash entry

#### Inputs

* `cash_entry_mode = UPSTREAM_PROVIDED`

#### Required outcome

* the engine does not auto-generate a duplicate cash entry
* the external cash transaction is accepted and linked
* income-side and cash-side effects remain reconcilable

---

## 15. DIVIDEND Decision Tables

### 15.1 Gross/net source decision table

| Condition                         | Required behavior                                                                   |
| --------------------------------- | ----------------------------------------------------------------------------------- |
| Upstream sends gross              | Derive withholding/net from gross                                                   |
| Upstream sends net only           | Preserve net, derive/require gross per policy or park if gross visibility mandatory |
| Upstream sends both gross and net | Reconcile within tolerance                                                          |

### 15.2 Withholding-tax decision table

| Condition            | Required behavior                                 |
| -------------------- | ------------------------------------------------- |
| Tax applies          | Preserve gross, tax, and net separately           |
| Tax does not apply   | Withholding tax = 0                               |
| Tax reclaim eligible | Preserve reclaimable component if policy requires |

### 15.3 Return-of-capital decision table

| Condition                                                | Required behavior                                           |
| -------------------------------------------------------- | ----------------------------------------------------------- |
| No ROC                                                   | Ordinary income = gross dividend                            |
| ROC present and policy reduces basis                     | Separate ROC and reduce cost basis                          |
| ROC present but policy does not reduce basis immediately | Preserve ROC separately and defer basis handling per policy |

### 15.4 Cash-entry mode decision table

| Condition                | Required behavior                                                            |
| ------------------------ | ---------------------------------------------------------------------------- |
| `AUTO_GENERATE`          | Engine generates linked cash entry                                           |
| `UPSTREAM_PROVIDED`      | Engine expects and links external cash entry                                 |
| Linked cash arrives late | Income-side record remains traceable and pending reconciliation until linked |

### 15.5 Timing decision table

| Condition                                | Required behavior                              |
| ---------------------------------------- | ---------------------------------------------- |
| `income_effective_timing = PAYMENT_DATE` | Income recognized on payment date              |
| `income_effective_timing = RECORD_DATE`  | Income recognized on record date               |
| `cash_effective_timing = PAYMENT_DATE`   | Cash booked on payment date                    |
| `cash_effective_timing = BOOKING_DATE`   | Cash booked on booking date if policy requires |

---

## 16. DIVIDEND Test Matrix

The implementation is not complete unless the following test categories are covered.

### 16.1 Validation tests

* accept valid standard `DIVIDEND`
* reject negative gross dividend
* reject negative withholding tax
* reject negative ROC amount
* reject missing payment date
* reject missing instrument identifier
* reject missing portfolio identifier
* reject invalid enum values
* reject gross/net mismatch beyond tolerance
* reject policy conflicts

### 16.2 Calculation tests

* ordinary cash dividend with withholding tax
* ordinary cash dividend without withholding tax
* gross supplied directly
* rate × quantity-derived dividend
* cross-currency dividend
* return-of-capital distribution
* tax reclaim eligible representation
* explicit zero realized P&L fields

### 16.3 Position tests

* no quantity change
* no lot creation
* no lot consumption
* no cost-basis change for ordinary dividend
* cost-basis reduction for ROC distribution under policy

### 16.4 Cash and dual-accounting tests

* auto-generated linked cash entry
* upstream-provided linked cash entry
* duplicate cash prevention
* linkage integrity
* same-currency settlement cash
* cross-currency settlement cash
* payment-date cash effect
* alternative timing cash effect if configured

### 16.5 Tax and ROC tests

* gross/tax/net preserved
* no withholding case
* withholding tax as supplied amount
* withholding tax as derived rate
* ROC separated from ordinary income
* ROC reduces cost basis when policy requires
* ROC preserved without immediate basis reduction when policy requires

### 16.6 Query tests

* enriched transaction visibility
* income visibility
* tax visibility
* cash linkage visibility
* ROC visibility
* policy metadata visibility

### 16.7 Idempotency and replay tests

* same transaction replay does not duplicate business effects
* duplicate `DIVIDEND` detection
* duplicate linked cash prevention
* replay-safe regeneration of derived state
* late-arriving linked cash reconciles correctly

### 16.8 Failure-mode tests

* validation hard-fail
* park pending remediation
* retryable processing failure
* terminal processing failure
* partial processing with explicit state visibility

---

## 17. DIVIDEND Edge Cases and Failure Cases

### 17.1 Edge cases

The engine must explicitly handle:

* zero gross dividend
* zero withholding tax
* zero return of capital
* missing ex-date with valid payment-date booking
* cross-currency dividend without required FX
* supplied gross mismatch versus per-unit derivation
* dividend booked without entitled quantity where allowed
* dividend with late linked cash entry
* dividend replay / duplicate arrival
* full net dividend equals zero due to tax/deductions
* gross known but tax unknown under strict policy

### 17.2 Failure cases

The engine must explicitly define behavior for:

* validation failure
* referential integrity failure
* policy-resolution failure
* reconciliation failure
* duplicate detection conflict
* linked cash missing beyond expected SLA
* event publish failure after local persistence
* query-read-model lag or partial propagation
* entitlement check failure when mandatory

### 17.3 Failure semantics requirement

For each failure class, the system must define:

* status
* reason code
* whether retriable
* whether blocking
* whether user-visible
* what operational action is required

---

## 18. DIVIDEND Configurable Policies

All material `DIVIDEND` behavior must be configurable through versioned policy, not code forks.

### 18.1 Mandatory configurable dimensions

The following must be configurable:

* gross supplied vs derived
* quantity/rate reconciliation tolerance
* precision rules
* FX precision
* withholding-tax treatment
* tax reclaim tracking
* return-of-capital treatment
* whether ROC reduces cost basis immediately
* cash-entry mode
* income timing
* cash timing
* performance timing
* linkage enforcement
* duplicate/replay handling
* strictness of entitlement validation

### 18.2 Policy traceability

Every processed `DIVIDEND` must preserve:

* `calculation_policy_id`
* `calculation_policy_version`

### 18.3 Policy conflict rule

If two policies or policy fragments conflict in a way that changes a material outcome, the engine must not silently choose one. It must fail or park according to policy-resolution rules.

---

## 19. DIVIDEND Gap Assessment Checklist

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

### 19.1 Characterization rule

If the current implementation already matches a requirement in this RFC, that behavior must be locked with characterization tests before refactoring or enhancement.

### 19.2 Completion rule

`DIVIDEND` is complete only when:

* the full input contract is implemented
* all mandatory validations are enforced
* all mandatory calculations are implemented
* withholding-tax support is implemented
* return-of-capital support is implemented
* dual-accounting support is implemented
* timing behavior is implemented
* all required metadata is preserved
* all required query outputs are available
* invariants are enforced
* the required test matrix is complete
* all remaining gaps are explicitly documented and approved

---

## 20. Appendices

### Appendix A: Error and Reason Codes

The platform must maintain a supporting catalog for:

* validation errors
* reconciliation mismatches
* policy-resolution failures
* linkage failures
* duplicate/replay conflicts
* entitlement failures
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

Subsequent transaction RFCs (such as `INTEREST`, `TRANSFER_IN`) must follow the same structural pattern as this `DIVIDEND` RFC to ensure consistency across:

* engineering implementation
* AI-assisted coding
* QA and regression
* BA analysis
* support and ops runbooks
* audit and reconciliation

---

## 21. Final Authoritative Statement

This RFC is the canonical specification for `DIVIDEND`.

If an implementation, test, support workflow, or downstream consumer behavior conflicts with this document, this document is the source of truth unless an approved exception or superseding RFC version explicitly states otherwise.
