# RFC-INTEREST-01 Canonical INTEREST Transaction Specification

## 1. Document Metadata

* **Document ID:** RFC-INTEREST-01
* **Title:** Canonical INTEREST Transaction Specification
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
| 1.0.0   | *TBD* | *TBD*  | Initial canonical INTEREST specification |

### 1.2 Purpose

This document defines the canonical, target-state specification for processing an `INTEREST` transaction in a private-banking / wealth-tech platform.

This RFC is the source of truth for:

* business semantics
* implementation behavior
* AI-assisted code generation
* automated testing
* validation and regression control
* BA analysis
* operations and support runbooks
* reconciliation and audit

Any implementation of `INTEREST` must conform to this specification unless an approved exception is explicitly documented.

### 1.3 Scope

This RFC applies to all booked `INTEREST` transactions that represent cash income or expense arising from interest-bearing balances or instruments, including but not limited to:

* bond coupon receipts booked as interest
* money market interest
* cash account credit interest
* cash account debit interest
* margin / overdraft interest charges
* accrued interest adjustments booked as standalone interest flows
* gross and net interest representations
* withholding-tax-adjusted interest receipts

This RFC covers:

* input contract
* validation
* enrichment
* policy resolution
* calculation
* income or expense recognition
* withholding-tax handling where applicable
* cash impact
* timing semantics
* linkage semantics
* query visibility
* observability
* test requirements

### 1.4 Out of Scope

This RFC does not define:

* buy/sell trade processing
* stock dividends / bonus shares
* corporate action transformations outside interest booking
* cancel / correct / rebook flows
* loan amortization principal movements unless represented as separate transaction types
* external settlement messaging workflows beyond required integration fields

Where out-of-scope processes interact with `INTEREST`, only the required interfaces, identifiers, and linkage expectations are defined here.

---

## 2. Referenced Shared Standards

This RFC must be read together with the shared transaction-processing standards in the repository.

### 2.1 Foundational shared standards

The following shared documents are normative for `INTEREST` unless explicitly overridden here:

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

This RFC defines all `INTEREST`-specific behavior.

If a shared document defines a generic rule and this RFC defines an `INTEREST`-specific specialization, the `INTEREST`-specific rule in this RFC takes precedence for `INTEREST` processing only.

---

## 3. INTEREST Business Definition

An `INTEREST` transaction represents recognition of interest income or interest expense arising from an interest-bearing asset, liability, or cash balance.

An `INTEREST` must:

* recognize income or expense
* optionally recognize withholding tax
* create or link a corresponding cash movement
* preserve gross vs net visibility
* preserve sufficient information for accounting, tax, reporting, reconciliation, and audit

An `INTEREST` must not:

* change instrument quantity
* create or consume acquisition lots
* create realized capital P&L
* create realized FX P&L
* be treated as a buy/sell disposal event

### 3.1 Non-negotiable semantic invariant

An `INTEREST` transaction recognizes interest income or interest expense, may recognize withholding tax, creates settlement cash movement, and must not change quantity, lot state, or realized capital/FX P&L.

### 3.2 Instrument-neutral rule

The same semantic model must apply across all supported interest-bearing assets and liabilities, with policy-driven variations for:

* income vs expense direction
* gross vs net receipt/payment representation
* withholding-tax treatment
* timing
* cash-entry mode
* precision and reconciliation behavior

### 3.3 Income vs expense rule

`INTEREST` must support both:

* **interest income**: increases cash and recognizes income
* **interest expense**: decreases cash and recognizes expense

The direction must be explicit and must not be inferred ambiguously from sign alone.

---

## 4. INTEREST Semantic Invariants

The following invariants are mandatory for every valid `INTEREST`.

### 4.1 Semantic invariants

* An `INTEREST` transaction must not change position quantity.
* An `INTEREST` transaction must not create or consume lots.
* An `INTEREST` transaction must recognize gross interest, net interest, or both according to policy.
* An `INTEREST` transaction must create settlement cash inflow or outflow, or explicit linked external cash expectation.
* An `INTEREST` transaction must preserve withholding-tax visibility if tax applies.
* An `INTEREST` transaction must not create realized capital P&L.
* An `INTEREST` transaction must not create realized FX P&L.
* An `INTEREST` transaction must not be classified as an investment buy/sell flow.

### 4.2 Numeric invariants

* `quantity_delta = 0`
* `gross_interest_local >= 0`
* `gross_interest_base >= 0`
* `withholding_tax_local >= 0`
* `withholding_tax_base >= 0`
* `net_interest_local >= 0`
* `net_interest_base >= 0`
* `net_interest = gross_interest - withholding_tax - other_interest_deductions`
* realized capital P&L local = `0`
* realized FX P&L local = `0`
* realized total P&L local = `0`
* realized capital P&L base = `0`
* realized FX P&L base = `0`
* realized total P&L base = `0`

### 4.3 Linkage invariants

* Every `INTEREST` transaction must have a stable `economic_event_id`.
* Every `INTEREST` transaction must have a stable `linked_transaction_group_id`.
* If cash is auto-generated, the linked cash entry must exist.
* If cash is upstream-provided, the external cash expectation must be explicit and linkable.
* Income/expense-side and cash-side effects must be reconcilable to the same economic event.

### 4.4 Audit invariants

* Every derived value must be reproducible from source data, linked data, and policy configuration.
* The active policy id and version must be identifiable for every processed `INTEREST`.
* Source-system identity and traceability must be preserved.

---

## 5. INTEREST Processing Flow

The engine must process an `INTEREST` transaction in the following deterministic sequence.

### 5.1 Receive and ingest

The engine must:

* accept a raw `INTEREST` payload
* classify it as `INTEREST`
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
* gross/net interest policy
* withholding-tax treatment policy
* income-vs-expense policy
* cash-entry mode
* timing policy
* precision policy
* duplicate/replay policy

No material calculation may proceed without an active, identifiable policy.

### 5.5 Calculate

The engine must perform calculations in canonical order:

1. determine gross interest
2. determine withholding tax
3. determine other interest deductions
4. determine ordinary interest income or expense component
5. determine net interest cash amount
6. convert relevant amounts to base currency
7. emit explicit zero realized P&L values
8. determine cashflow instruction or linked cash expectation

### 5.6 Create business effects

The engine must produce:

* income or expense recognition effect
* tax effect
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

## 6. INTEREST Canonical Data Model

### 6.1 Top-level model

The canonical logical model must be `InterestTransaction`.

### 6.2 Required model composition

`InterestTransaction` must be composed of:

* `TransactionIdentity`
* `TransactionLifecycle`
* `InstrumentReference`
* `InterestEventDetails`
* `SettlementDetails`
* `AmountDetails`
* `TaxDetails`
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
| `transaction_id`              | `str`             |      Yes | UPSTREAM / DERIVED | IMMUTABLE  | Unique identifier of this transaction record                                  | `TXN-2026-000423` |
| `economic_event_id`           | `str`             |      Yes | DERIVED            | IMMUTABLE  | Shared identifier for all linked entries representing the same economic event | `EVT-2026-03987`  |
| `linked_transaction_group_id` | `str`             |      Yes | DERIVED            | IMMUTABLE  | Groups related entries such as the `INTEREST` and linked cash entry           | `LTG-2026-03456`  |
| `transaction_type`            | `TransactionType` |      Yes | UPSTREAM           | IMMUTABLE  | Canonical transaction type enum                                               | `INTEREST`        |

#### 6.5.2 TransactionLifecycle

| Field                | Type               | Required | Source                | Mutability | Description                               | Sample       |
| -------------------- | ------------------ | -------: | --------------------- | ---------- | ----------------------------------------- | ------------ |
| `accrual_start_date` | `date \| None`     |       No | UPSTREAM              | IMMUTABLE  | Start date of the interest accrual period | `2026-03-01` |
| `accrual_end_date`   | `date \| None`     |       No | UPSTREAM              | IMMUTABLE  | End date of the interest accrual period   | `2026-03-31` |
| `payment_date`       | `date`             |      Yes | UPSTREAM              | IMMUTABLE  | Contractual payment/charge date           | `2026-04-01` |
| `booking_date`       | `date \| None`     |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | Accounting booking date                   | `2026-04-01` |
| `value_date`         | `date \| None`     |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | Value date for ledger purposes            | `2026-04-01` |
| `interest_status`    | `InterestStatus`   |      Yes | UPSTREAM / CONFIGURED | RECOMPUTED | Processing state of the interest event    | `BOOKED`     |
| `settlement_status`  | `SettlementStatus` |      Yes | DERIVED / CONFIGURED  | RECOMPUTED | Settlement lifecycle status               | `PENDING`    |

#### 6.5.3 InstrumentReference

| Field                  | Type                 | Required | Source                | Mutability | Description                                              | Sample        |
| ---------------------- | -------------------- | -------: | --------------------- | ---------- | -------------------------------------------------------- | ------------- |
| `portfolio_id`         | `str`                |      Yes | UPSTREAM              | IMMUTABLE  | Portfolio receiving or paying the interest               | `PORT-10001`  |
| `instrument_id`        | `str \| None`        |       No | UPSTREAM              | IMMUTABLE  | Canonical instrument identifier if tied to an instrument | `USBOND-10Y`  |
| `security_id`          | `str \| None`        |       No | UPSTREAM              | IMMUTABLE  | Security master identifier if applicable                 | `US91282CJL6` |
| `interest_source_type` | `InterestSourceType` |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Source of interest such as cash, bond, margin, overdraft | `BOND_COUPON` |
| `cash_account_id`      | `str \| None`        |       No | UPSTREAM              | IMMUTABLE  | Cash account if interest is on cash balance              | `CASH-USD-01` |

#### 6.5.4 InterestEventDetails

| Field                        | Type                | Required | Source                | Mutability | Description                                            | Sample   |
| ---------------------------- | ------------------- | -------: | --------------------- | ---------- | ------------------------------------------------------ | -------- |
| `interest_direction`         | `InterestDirection` |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Whether the transaction is income or expense           | `INCOME` |
| `interest_type`              | `InterestType`      |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Type of interest event                                 | `COUPON` |
| `gross_or_net_indicator`     | `GrossNetIndicator` |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Whether upstream amount is gross or net                | `GROSS`  |
| `interest_rate_reference`    | `Decimal \| None`   |       No | UPSTREAM              | IMMUTABLE  | Rate used for informational or reconciliation purposes | `0.0425` |
| `withholding_tax_applicable` | `bool`              |      Yes | DERIVED / CONFIGURED  | IMMUTABLE  | Whether withholding tax applies                        | `false`  |

#### 6.5.5 SettlementDetails

| Field                         | Type              | Required | Source                | Mutability | Description                                             | Sample         |
| ----------------------------- | ----------------- | -------: | --------------------- | ---------- | ------------------------------------------------------- | -------------- |
| `cash_effective_timing`       | `EffectiveTiming` |      Yes | CONFIGURED            | IMMUTABLE  | When cash is increased or decreased for ledger purposes | `PAYMENT_DATE` |
| `income_effective_timing`     | `EffectiveTiming` |      Yes | CONFIGURED            | IMMUTABLE  | When income/expense is recognized                       | `PAYMENT_DATE` |
| `performance_cashflow_timing` | `EffectiveTiming` |      Yes | CONFIGURED            | IMMUTABLE  | When performance views recognize the interest cashflow  | `PAYMENT_DATE` |
| `settlement_currency`         | `str`             |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Currency in which cash is settled                       | `USD`          |
| `settlement_cash_account_id`  | `str \| None`     |       No | UPSTREAM              | IMMUTABLE  | Cash account affected by the interest receipt/payment   | `CASH-USD-01`  |

#### 6.5.6 AmountDetails

| Field                             | Type      | Required | Source             | Mutability   | Description                                  | Sample   |
| --------------------------------- | --------- | -------: | ------------------ | ------------ | -------------------------------------------- | -------- |
| `gross_interest_local`            | `Decimal` |      Yes | UPSTREAM / DERIVED | DERIVED_ONCE | Gross interest amount before tax             | `125.00` |
| `gross_interest_base`             | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Base-currency equivalent of gross interest   | `125.00` |
| `other_interest_deductions_local` | `Decimal` |      Yes | UPSTREAM / DERIVED | DERIVED_ONCE | Other deductions reducing cash settlement    | `0.00`   |
| `other_interest_deductions_base`  | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Base-currency equivalent of other deductions | `0.00`   |
| `net_interest_local`              | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Net interest cash settled                    | `125.00` |
| `net_interest_base`               | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Base-currency equivalent of net interest     | `125.00` |
| `settlement_cash_amount_local`    | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Cash movement amount in local currency       | `125.00` |
| `settlement_cash_amount_base`     | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Cash movement amount in base currency        | `125.00` |

#### 6.5.7 TaxDetails

| Field                        | Type              | Required | Source             | Mutability   | Description                                     | Sample |
| ---------------------------- | ----------------- | -------: | ------------------ | ------------ | ----------------------------------------------- | ------ |
| `withholding_tax_local`      | `Decimal`         |      Yes | UPSTREAM / DERIVED | DERIVED_ONCE | Tax withheld from gross interest                | `0.00` |
| `withholding_tax_base`       | `Decimal`         |      Yes | DERIVED            | DERIVED_ONCE | Base-currency equivalent of withholding tax     | `0.00` |
| `withholding_tax_rate`       | `Decimal \| None` |       No | UPSTREAM / DERIVED | DERIVED_ONCE | Applied withholding-tax rate                    | `0.10` |
| `tax_reclaim_eligible_local` | `Decimal \| None` |       No | DERIVED            | DERIVED_ONCE | Portion potentially reclaimable under policy    | `0.00` |
| `tax_reclaim_eligible_base`  | `Decimal \| None` |       No | DERIVED            | DERIVED_ONCE | Base-currency equivalent of reclaimable portion | `0.00` |

#### 6.5.8 FxDetails

| Field                     | Type              | Required | Source                | Mutability | Description                                       | Sample     |
| ------------------------- | ----------------- | -------: | --------------------- | ---------- | ------------------------------------------------- | ---------- |
| `interest_currency`       | `str`             |      Yes | UPSTREAM              | IMMUTABLE  | Currency in which the interest is stated          | `USD`      |
| `portfolio_base_currency` | `str`             |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Portfolio reporting base currency                 | `USD`      |
| `interest_fx_rate`        | `Decimal`         |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | FX rate from interest currency to base currency   | `1.000000` |
| `settlement_fx_rate`      | `Decimal \| None` |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | FX rate used for settlement currency if different | `1.000000` |
| `fx_rate_source`          | `str \| None`     |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | Source of FX rate used                            | `WMR_4PM`  |

#### 6.5.9 ClassificationDetails

| Field                        | Type                        | Required | Source               | Mutability | Description                                         | Sample                               |
| ---------------------------- | --------------------------- | -------: | -------------------- | ---------- | --------------------------------------------------- | ------------------------------------ |
| `transaction_classification` | `TransactionClassification` |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | High-level classification of the transaction        | `INCOME` or `EXPENSE`                |
| `cashflow_classification`    | `CashflowClassification`    |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Classification of the cash movement                 | `INCOME_INFLOW` or `EXPENSE_OUTFLOW` |
| `income_classification`      | `IncomeClassification`      |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Income classification applicable to the transaction | `INTEREST`                           |
| `tax_classification`         | `TaxClassification`         |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Tax classification of the withheld amount           | `WITHHOLDING_TAX`                    |

#### 6.5.10 PositionEffect

| Field                     | Type      | Required | Source  | Mutability   | Description                              | Sample |
| ------------------------- | --------- | -------: | ------- | ------------ | ---------------------------------------- | ------ |
| `position_quantity_delta` | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Quantity change caused by the `INTEREST` | `0`    |
| `cost_basis_delta_local`  | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Cost-basis change in local currency      | `0.00` |
| `cost_basis_delta_base`   | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Cost-basis change in base currency       | `0.00` |

#### 6.5.11 IncomeEffect

| Field                           | Type      | Required | Source  | Mutability   | Description                                        | Sample   |
| ------------------------------- | --------- | -------: | ------- | ------------ | -------------------------------------------------- | -------- |
| `ordinary_interest_local`       | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Ordinary interest income or expense before tax     | `125.00` |
| `ordinary_interest_base`        | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Base-currency equivalent of ordinary interest      | `125.00` |
| `net_interest_recognized_local` | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Net recognized amount after withholding/deductions | `125.00` |
| `net_interest_recognized_base`  | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Base-currency equivalent of net recognized amount  | `125.00` |

#### 6.5.12 RealizedPnlDetails

| Field                        | Type      | Required | Source  | Mutability   | Description                            | Sample |
| ---------------------------- | --------- | -------: | ------- | ------------ | -------------------------------------- | ------ |
| `realized_capital_pnl_local` | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized capital P&L in local currency | `0.00` |
| `realized_fx_pnl_local`      | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized FX P&L in local currency      | `0.00` |
| `realized_total_pnl_local`   | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Total realized P&L in local currency   | `0.00` |
| `realized_capital_pnl_base`  | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized capital P&L in base currency  | `0.00` |
| `realized_fx_pnl_base`       | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized FX P&L in base currency       | `0.00` |
| `realized_total_pnl_base`    | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Total realized P&L in base currency    | `0.00` |

#### 6.5.13 CashflowInstruction

| Field                          | Type            | Required | Source               | Mutability   | Description                                                      | Sample                 |
| ------------------------------ | --------------- | -------: | -------------------- | ------------ | ---------------------------------------------------------------- | ---------------------- |
| `cash_entry_mode`              | `CashEntryMode` |      Yes | CONFIGURED           | IMMUTABLE    | Whether cash entry is engine-generated or expected from upstream | `AUTO_GENERATE`        |
| `auto_generate_cash_entry`     | `bool`          |      Yes | DERIVED / CONFIGURED | IMMUTABLE    | Whether the engine must generate the linked cash entry           | `true`                 |
| `linked_cash_transaction_id`   | `str \| None`   |       No | LINKED / DERIVED     | RECOMPUTED   | Linked cash transaction identifier                               | `TXN-CASH-2026-000423` |
| `settlement_cash_amount_local` | `Decimal`       |      Yes | DERIVED              | DERIVED_ONCE | Cash movement amount in local currency                           | `125.00`               |
| `settlement_cash_amount_base`  | `Decimal`       |      Yes | DERIVED              | DERIVED_ONCE | Cash movement amount in base currency                            | `125.00`               |

#### 6.5.14 LinkageDetails

| Field                        | Type          | Required | Source               | Mutability | Description                                               | Sample             |
| ---------------------------- | ------------- | -------: | -------------------- | ---------- | --------------------------------------------------------- | ------------------ |
| `originating_transaction_id` | `str \| None` |       No | LINKED               | IMMUTABLE  | Source transaction for linked entries                     | `TXN-2026-000423`  |
| `link_type`                  | `LinkType`    |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Semantic meaning of the transaction linkage               | `INTEREST_TO_CASH` |
| `reconciliation_key`         | `str \| None` |       No | UPSTREAM / DERIVED   | IMMUTABLE  | Key used to reconcile with upstream or accounting systems | `RECON-JKL-012`    |

#### 6.5.15 AuditMetadata

| Field                | Type               | Required | Source             | Mutability | Description                             | Sample                 |
| -------------------- | ------------------ | -------: | ------------------ | ---------- | --------------------------------------- | ---------------------- |
| `source_system`      | `str`              |      Yes | UPSTREAM           | IMMUTABLE  | Originating system name                 | `INTEREST_ENGINE`      |
| `external_reference` | `str \| None`      |       No | UPSTREAM           | IMMUTABLE  | Upstream external reference             | `EXT-999222`           |
| `booking_center`     | `str \| None`      |       No | UPSTREAM           | IMMUTABLE  | Booking center / legal booking location | `SGPB`                 |
| `created_at`         | `datetime`         |      Yes | UPSTREAM / DERIVED | IMMUTABLE  | Record creation timestamp               | `2026-04-01T08:00:00Z` |
| `processed_at`       | `datetime \| None` |       No | DERIVED            | RECOMPUTED | Processing completion timestamp         | `2026-04-01T08:00:02Z` |

#### 6.5.16 AdvisoryMetadata

| Field                   | Type          | Required | Source   | Mutability | Description                                          | Sample           |
| ----------------------- | ------------- | -------: | -------- | ---------- | ---------------------------------------------------- | ---------------- |
| `advisor_id`            | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Relationship manager / advisor reference if relevant | `RM-1001`        |
| `client_instruction_id` | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Client instruction reference if manually booked      | `CI-2026-7802`   |
| `mandate_reference`     | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Mandate linkage if relevant                          | `DPM-MANDATE-01` |

#### 6.5.17 PolicyMetadata

| Field                        | Type  | Required | Source     | Mutability | Description                                         | Sample                        |
| ---------------------------- | ----- | -------: | ---------- | ---------- | --------------------------------------------------- | ----------------------------- |
| `calculation_policy_id`      | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy identifier used for this calculation         | `POLICY-INT-STD`              |
| `calculation_policy_version` | `str` |      Yes | CONFIGURED | IMMUTABLE  | Version of the calculation policy applied           | `1.0.0`                       |
| `withholding_tax_policy`     | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy controlling withholding-tax treatment        | `PRESERVE_GROSS_AND_NET`      |
| `interest_direction_policy`  | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy controlling income vs expense interpretation | `EXPLICIT_DIRECTION_REQUIRED` |
| `cash_generation_policy`     | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy controlling how cash entries are created     | `AUTO_GENERATE_LINKED_CASH`   |

---

## 7. INTEREST Validation Rules

### 7.1 Mandatory required-field validation

A valid `INTEREST` transaction must include, at minimum:

* transaction identity
* transaction type
* payment date
* portfolio identifier
* gross amount or reconcilable rate-based amount
* interest currency
* portfolio base currency
* applicable FX rate
* explicit interest direction
* required policy identifiers if not resolved externally

### 7.2 Numeric validation

The engine must enforce:

* `gross_interest_local >= 0`
* `withholding_tax_local >= 0`
* `other_interest_deductions_local >= 0`
* `interest_fx_rate > 0`
* `settlement_fx_rate > 0` when present
* all numeric fields must be decimal-safe
* all numeric fields must satisfy configured precision rules

### 7.3 Reconciliation validation

If both supplied total amount and derived rate-based values are available:

* the engine must reconcile them
* tolerance must be policy-driven
* out-of-tolerance mismatches must fail or park according to policy

### 7.4 Enum validation

The engine must validate all enum-constrained fields, including:

* transaction type
* transaction classification
* cashflow classification
* income classification
* timing values
* interest status
* settlement status
* cash-entry mode
* link type
* interest direction
* interest type

### 7.5 Referential validation

The engine must validate, where required:

* portfolio reference exists
* instrument or cash-account reference exists when applicable
* cash account reference exists when explicit account linkage is required
* linked transaction identifiers are valid when separate cash-entry mode is used

### 7.6 Validation outcomes

Each validation failure must resolve to one of:

* `HARD_REJECT`
* `PARK_PENDING_REMEDIATION`
* `ACCEPT_WITH_WARNING`
* `RETRYABLE_FAILURE`
* `TERMINAL_FAILURE`

The applicable outcome must be deterministic and policy-driven.

### 7.7 INTEREST-specific hard-fail conditions

The following must hard-fail unless explicitly configured otherwise:

* negative gross interest
* missing payment date
* missing portfolio identifier
* invalid transaction type
* missing explicit interest direction
* cross-currency interest with missing required FX rate
* negative withholding tax
* policy conflict affecting a material calculation

---

## 8. INTEREST Calculation Rules and Formulas

### 8.1 Input values

The engine must support calculation from the following normalized inputs:

* gross interest supplied value where present
* rate-based interest amount where present
* withholding tax amount or rate
* other interest deductions
* interest currency
* settlement currency where relevant
* portfolio base currency
* interest FX rate
* settlement FX rate where relevant

### 8.2 Derived values

The engine must derive, at minimum:

* `gross_interest_local`
* `gross_interest_base`
* `withholding_tax_local`
* `withholding_tax_base`
* `other_interest_deductions_local`
* `other_interest_deductions_base`
* `ordinary_interest_local`
* `ordinary_interest_base`
* `net_interest_local`
* `net_interest_base`
* `settlement_cash_amount_local`
* `settlement_cash_amount_base`
* explicit realized P&L zero values

### 8.3 Canonical formula order

The engine must calculate in this exact order:

1. determine `gross_interest_local`
2. determine `withholding_tax_local`
3. determine `other_interest_deductions_local`
4. determine ordinary interest amount
5. determine `net_interest_local`
6. convert required values into base currency
7. emit explicit zero realized P&L fields
8. determine linked cash behavior

### 8.4 Gross interest calculation

If `gross_interest_local` is not explicitly supplied and rate data is available, it may be derived under policy from the relevant accrual basis.

If `gross_interest_local` is supplied, it must reconcile with the derived value within configured tolerance where both are available.

### 8.5 Withholding tax calculation

If withholding tax is supplied as a rate:

`withholding_tax_local = gross_interest_local × withholding_tax_rate`

If withholding tax is supplied as an amount, it must reconcile to any rate-derived value within configured tolerance where both are available.

### 8.6 Net interest calculation

By default:

`net_interest_local = gross_interest_local - withholding_tax_local - other_interest_deductions_local`

### 8.7 Settlement cash calculation

For `interest_direction = INCOME` by default:

`settlement_cash_amount_local = net_interest_local`

For `interest_direction = EXPENSE` by default:

`settlement_cash_amount_local = net_interest_local`

with cashflow sign and classification determining the outflow effect.

### 8.8 Base-currency conversion

The engine must convert all relevant local amounts to base currency using the active FX policy.

By default:

`amount_base = amount_local × applicable_fx_rate`

The FX source, precision, and rounding behavior must be policy-driven and traceable.

### 8.9 Realized P&L fields

For every `INTEREST`, the engine must explicitly produce:

* realized capital P&L local = `0`
* realized FX P&L local = `0`
* realized total P&L local = `0`
* realized capital P&L base = `0`
* realized FX P&L base = `0`
* realized total P&L base = `0`

These fields must be present and must not be omitted.

### 8.10 Rounding and precision

The engine must define:

* internal calculation precision
* rounding scale per amount type
* rounding mode
* presentation scale
* FX conversion rounding rules
* reconciliation tolerance rules

Rounding must be applied only at defined calculation boundaries and must not vary by implementation.

---

## 9. INTEREST Position Rules

### 9.1 Quantity effect

An `INTEREST` transaction must not change position quantity.

`new_quantity = old_quantity`

### 9.2 Cost-basis effect

By default, an `INTEREST` transaction must not change cost basis.

### 9.3 Held-since behavior

An `INTEREST` transaction must not change `held_since_date`.

### 9.4 Position rule invariants

* Position quantity must remain unchanged.
* No lots may be created or consumed.
* Cost basis must remain unchanged.

---

## 10. INTEREST Cash and Dual-Accounting Rules

### 10.1 Core cash rule

An `INTEREST` transaction must create a cash movement.

### 10.2 Directional cash rule

* For `interest_direction = INCOME`, cash increases.
* For `interest_direction = EXPENSE`, cash decreases.

### 10.3 Required cash concepts

The engine must support:

* gross interest amount
* tax deductions
* net settlement cash amount

### 10.4 Settlement cash rule

By default:

* for income: `settlement_cash_amount_local = net_interest_local`
* for expense: `settlement_cash_amount_local = net_interest_local`

with direction represented by classification and sign conventions in the cash ledger.

### 10.5 Cash-entry modes

The system must support both:

* `AUTO_GENERATE`
* `UPSTREAM_PROVIDED`

### 10.6 Auto-generated cash mode

If `cash_entry_mode = AUTO_GENERATE`:

* the engine must create a linked cash entry
* the linked cash entry must increase or decrease cash according to direction
* the entry must be linked to the originating `INTEREST`

### 10.7 Upstream-provided cash mode

If `cash_entry_mode = UPSTREAM_PROVIDED`:

* the engine must not generate a duplicate cash entry
* the engine must accept a separate upstream cash transaction
* the engine must link that cash transaction to the `INTEREST`

### 10.8 Required linkage fields

Interest-side and cash-side entries must be linkable through:

* `economic_event_id`
* `linked_transaction_group_id`
* `originating_transaction_id`
* `linked_cash_transaction_id`
* `link_type`
* `reconciliation_key` where applicable

### 10.9 Cash balance views

The platform must distinguish, where relevant:

* available cash
* settled cash
* projected cash
* ledger cash

### 10.10 Cash invariants

* An `INTEREST` cash effect must always be linked or explicitly externally expected.
* Duplicate cash creation must be prevented.
* Cash-side and interest-side effects must reconcile to the same economic event.

---

## 11. INTEREST Tax Rules

### 11.1 Withholding-tax rule

If withholding tax applies:

* gross interest must remain visible
* withholding tax must remain visible
* net cash settled must remain visible

The engine must not preserve only net cash and discard gross/tax decomposition.

### 11.2 Tax reporting rule

Withholding tax must be separately classifiable and reportable for:

* tax reporting
* statement reporting
* reclaim workflows where relevant

### 11.3 Tax invariants

* Withholding tax must never be merged indistinguishably into net cash.
* Tax treatment must be policy-driven, explicit, and reportable.

---

## 12. INTEREST Timing Rules

### 12.1 Timing dimensions

The engine must support these timing dimensions independently:

* income recognition timing
* cash timing
* performance timing
* reporting timing

### 12.2 Supported timing values

Supported values must include:

* `ACCRUAL_END_DATE`
* `PAYMENT_DATE`
* `BOOKING_DATE`

### 12.3 Income recognition timing

The system must support interest recognition under the configured policy, typically on:

* payment date, or
* accrual end date, where institution policy requires accrual-style recognition

### 12.4 Cash timing

Cash is typically realized on payment date, but the system must support policy-driven variants.

### 12.5 Performance timing

The system must support performance recognition under the configured performance timing policy.

### 12.6 Timing invariants

* Timing behavior must be policy-driven, explicit, and auditable.
* Different timing modes must not silently distort income/expense, cash, and reporting views.

---

## 13. INTEREST Query / Output Contract

### 13.1 Required query surfaces

After successful processing, the platform must expose:

* enriched transaction view
* income/expense view
* cash linkage view
* tax view
* audit view

### 13.2 Required transaction output fields

At minimum, downstream consumers must be able to retrieve:

* canonical transaction identifiers
* core business fields
* gross/net/tax decomposition
* direction classification
* timing fields
* policy metadata
* explicit realized P&L structure
* linkage fields

### 13.3 Required income/expense output fields

At minimum:

* ordinary interest local/base
* net interest local/base
* withholding tax local/base
* income/expense direction

### 13.4 Required position output fields

At minimum:

* unchanged quantity
* unchanged cost basis
* no lot creation/consumption indicator

### 13.5 Consistency expectation

The platform must define whether these surfaces are:

* synchronous
* eventually consistent

and must document the expected latency/SLA for visibility.

---

## 14. INTEREST Worked Examples

### 14.1 Example A: Bond coupon interest income

#### Inputs

* interest direction: `INCOME`
* interest type: `COUPON`
* gross interest local: `125.00`
* withholding tax local: `0.00`
* other deductions: `0.00`
* interest currency: `USD`
* portfolio base currency: `USD`
* interest FX rate: `1.000000`
* cash entry mode: `AUTO_GENERATE`

#### Derivations

* `ordinary_interest_local = 125.00`
* `net_interest_local = 125.00 - 0.00 - 0.00 = 125.00`
* `settlement_cash_amount_local = 125.00`
* base equivalents are identical
* realized P&L fields = `0.00`

#### Expected outputs

* no quantity change
* no lot activity
* linked cash entry increases cash by `125.00`
* interest income recorded as `125.00`

#### Invariants checked

* gross and net visible
* no realized capital P&L
* not classified as investment buy/sell

---

### 14.2 Example B: Cash account credit interest with withholding tax

#### Inputs

* interest direction: `INCOME`
* interest type: `CASH_CREDIT`
* gross interest local: `20.00`
* withholding tax rate: `0.10`
* other deductions: `0.00`

#### Derivations

* `withholding_tax_local = 20.00 × 0.10 = 2.00`
* `net_interest_local = 20.00 - 2.00 = 18.00`
* `settlement_cash_amount_local = 18.00`

#### Expected outputs

* gross interest = `20.00`
* withholding tax = `2.00`
* net cash received = `18.00`
* no quantity change

---

### 14.3 Example C: Margin interest expense

#### Inputs

* interest direction: `EXPENSE`
* interest type: `MARGIN_DEBIT`
* gross interest local: `35.00`
* withholding tax local: `0.00`
* other deductions: `0.00`
* interest currency: `USD`

#### Derivations

* `ordinary_interest_local = 35.00`
* `net_interest_local = 35.00`
* `settlement_cash_amount_local = 35.00`

#### Expected outputs

* no quantity change
* linked cash entry decreases cash by `35.00`
* transaction classified as expense
* realized P&L remains zero

---

### 14.4 Example D: Cross-currency interest income

#### Inputs

* gross interest local: `125.00 USD`
* withholding tax local: `0.00 USD`
* interest FX rate: `1.350000`
* base currency: `SGD`

#### Derivations

* `gross_interest_base = 125.00 × 1.35 = 168.75`
* `net_interest_base = 125.00 × 1.35 = 168.75`
* `settlement_cash_amount_base = 168.75`

#### Expected outputs

* local and base interest amounts populated
* no realized FX P&L
* FX conversion remains explicit and traceable

---

### 14.5 Example E: Auto-generated cash entry

#### Inputs

* `cash_entry_mode = AUTO_GENERATE`

#### Required outcome

* the engine generates a linked cash entry
* the cash entry has the same `economic_event_id`
* `originating_transaction_id` links back to the `INTEREST`
* no duplicate cash entry may be produced on replay

---

### 14.6 Example F: Upstream-provided cash entry

#### Inputs

* `cash_entry_mode = UPSTREAM_PROVIDED`

#### Required outcome

* the engine does not auto-generate a duplicate cash entry
* the external cash transaction is accepted and linked
* interest-side and cash-side effects remain reconcilable

---

## 15. INTEREST Decision Tables

### 15.1 Direction decision table

| Condition                      | Required behavior                   |
| ------------------------------ | ----------------------------------- |
| `interest_direction = INCOME`  | Recognize income and increase cash  |
| `interest_direction = EXPENSE` | Recognize expense and decrease cash |

### 15.2 Gross/net source decision table

| Condition                         | Required behavior                                                                   |
| --------------------------------- | ----------------------------------------------------------------------------------- |
| Upstream sends gross              | Derive withholding/net from gross                                                   |
| Upstream sends net only           | Preserve net, derive/require gross per policy or park if gross visibility mandatory |
| Upstream sends both gross and net | Reconcile within tolerance                                                          |

### 15.3 Withholding-tax decision table

| Condition            | Required behavior                                 |
| -------------------- | ------------------------------------------------- |
| Tax applies          | Preserve gross, tax, and net separately           |
| Tax does not apply   | Withholding tax = 0                               |
| Tax reclaim eligible | Preserve reclaimable component if policy requires |

### 15.4 Cash-entry mode decision table

| Condition                | Required behavior                                                              |
| ------------------------ | ------------------------------------------------------------------------------ |
| `AUTO_GENERATE`          | Engine generates linked cash entry                                             |
| `UPSTREAM_PROVIDED`      | Engine expects and links external cash entry                                   |
| Linked cash arrives late | Interest-side record remains traceable and pending reconciliation until linked |

### 15.5 Timing decision table

| Condition                                    | Required behavior                              |
| -------------------------------------------- | ---------------------------------------------- |
| `income_effective_timing = PAYMENT_DATE`     | Interest recognized on payment date            |
| `income_effective_timing = ACCRUAL_END_DATE` | Interest recognized at end of accrual period   |
| `cash_effective_timing = PAYMENT_DATE`       | Cash booked on payment date                    |
| `cash_effective_timing = BOOKING_DATE`       | Cash booked on booking date if policy requires |

---

## 16. INTEREST Test Matrix

The implementation is not complete unless the following test categories are covered.

### 16.1 Validation tests

* accept valid standard `INTEREST`
* reject negative gross interest
* reject negative withholding tax
* reject missing payment date
* reject missing portfolio identifier
* reject invalid enum values
* reject gross/net mismatch beyond tolerance
* reject policy conflicts
* reject missing explicit direction

### 16.2 Calculation tests

* ordinary coupon interest income
* cash credit interest with withholding tax
* gross supplied directly
* rate-derived interest where supported
* cross-currency interest
* margin/overdraft interest expense
* explicit zero realized P&L fields

### 16.3 Position tests

* no quantity change
* no lot creation
* no lot consumption
* no cost-basis change

### 16.4 Cash and dual-accounting tests

* auto-generated linked cash entry
* upstream-provided linked cash entry
* duplicate cash prevention
* linkage integrity
* same-currency settlement cash
* cross-currency settlement cash
* payment-date cash effect
* alternative timing cash effect if configured
* income direction inflow
* expense direction outflow

### 16.5 Tax tests

* gross/tax/net preserved
* no withholding case
* withholding tax as supplied amount
* withholding tax as derived rate
* reclaimable tax representation where supported

### 16.6 Query tests

* enriched transaction visibility
* income/expense visibility
* tax visibility
* cash linkage visibility
* policy metadata visibility

### 16.7 Idempotency and replay tests

* same transaction replay does not duplicate business effects
* duplicate `INTEREST` detection
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

## 17. INTEREST Edge Cases and Failure Cases

### 17.1 Edge cases

The engine must explicitly handle:

* zero gross interest
* zero withholding tax
* missing accrual dates with valid payment-date booking
* cross-currency interest without required FX
* supplied gross mismatch versus rate derivation
* interest booked without instrument_id for cash-account interest where allowed
* interest with late linked cash entry
* interest replay / duplicate arrival
* full net interest equals zero due to tax/deductions
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

### 17.3 Failure semantics requirement

For each failure class, the system must define:

* status
* reason code
* whether retriable
* whether blocking
* whether user-visible
* what operational action is required

---

## 18. INTEREST Configurable Policies

All material `INTEREST` behavior must be configurable through versioned policy, not code forks.

### 18.1 Mandatory configurable dimensions

The following must be configurable:

* gross supplied vs derived
* rate-based reconciliation tolerance
* precision rules
* FX precision
* withholding-tax treatment
* tax reclaim tracking
* income vs expense handling
* cash-entry mode
* income timing
* cash timing
* performance timing
* linkage enforcement
* duplicate/replay handling
* strictness of referential validation for instrument vs cash interest

### 18.2 Policy traceability

Every processed `INTEREST` must preserve:

* `calculation_policy_id`
* `calculation_policy_version`

### 18.3 Policy conflict rule

If two policies or policy fragments conflict in a way that changes a material outcome, the engine must not silently choose one. It must fail or park according to policy-resolution rules.

---

## 19. INTEREST Gap Assessment Checklist

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

`INTEREST` is complete only when:

* the full input contract is implemented
* all mandatory validations are enforced
* all mandatory calculations are implemented
* withholding-tax support is implemented
* income/expense directional support is implemented
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

Subsequent transaction RFCs must follow the same structural pattern as this `INTEREST` RFC to ensure consistency across:

* engineering implementation
* AI-assisted coding
* QA and regression
* BA analysis
* support and ops runbooks
* audit and reconciliation

---

## 21. Final Authoritative Statement

This RFC is the canonical specification for `INTEREST`.

If an implementation, test, support workflow, or downstream consumer behavior conflicts with this document, this document is the source of truth unless an approved exception or superseding RFC version explicitly states otherwise.
