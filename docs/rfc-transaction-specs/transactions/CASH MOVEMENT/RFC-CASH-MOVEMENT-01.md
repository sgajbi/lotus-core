# RFC-CASH-MOVEMENT-01 Canonical DEPOSIT and WITHDRAWAL Transaction Specification

## 1. Document Metadata

* **Document ID:** RFC-CASH-MOVEMENT-01
* **Title:** Canonical DEPOSIT and WITHDRAWAL Transaction Specification
* **Version:** 1.0.0
* **Status:** Draft
* **Owner:** *TBD*
* **Reviewers:** *TBD*
* **Approvers:** *TBD*
* **Last Updated:** *TBD*
* **Effective Date:** *TBD*

### 1.1 Change Log

| Version | Date  | Author | Summary                                                |
| ------- | ----- | ------ | ------------------------------------------------------ |
| 1.0.0   | *TBD* | *TBD*  | Initial canonical DEPOSIT and WITHDRAWAL specification |

### 1.2 Purpose

This document defines the canonical, target-state specification for processing `DEPOSIT` and `WITHDRAWAL` transactions in a private-banking / wealth-tech platform.

This RFC is the source of truth for:

* business semantics
* implementation behavior
* AI-assisted code generation
* automated testing
* validation and regression control
* BA analysis
* operations and support runbooks
* reconciliation and audit

Any implementation of `DEPOSIT` or `WITHDRAWAL` must conform to this specification unless an approved exception is explicitly documented.

### 1.3 Scope

This RFC applies to all booked cash funding and cash removal transactions, including but not limited to:

* external cash deposits into portfolio cash accounts
* external cash withdrawals from portfolio cash accounts
* client funding and redemption cash movements
* internal booking-center cash movements when classified as deposit/withdrawal by policy
* gross and net cash movement representations
* fee-adjusted deposits and withdrawals where applicable

This RFC covers:

* input contract
* validation
* enrichment
* policy resolution
* calculation
* cash-balance impact
* portfolio-flow classification
* timing semantics
* linkage semantics
* query visibility
* observability
* test requirements

### 1.4 Out of Scope

This RFC does not define:

* security buy/sell trade processing
* FX spot or transfer conversions unless separately represented
* fee transactions booked as standalone `FEE`
* interest, dividend, or income events
* cancel / correct / rebook flows
* external payment-network message formats beyond required integration fields

Where out-of-scope processes interact with `DEPOSIT` or `WITHDRAWAL`, only the required interfaces, identifiers, and linkage expectations are defined here.

---

## 2. Referenced Shared Standards

This RFC must be read together with the shared transaction-processing standards in the repository.

### 2.1 Foundational shared standards

The following shared documents are normative for `DEPOSIT` and `WITHDRAWAL` unless explicitly overridden here:

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

This RFC defines all `DEPOSIT`- and `WITHDRAWAL`-specific behavior.

If a shared document defines a generic rule and this RFC defines a cash-movement-specific specialization, the rule in this RFC takes precedence for `DEPOSIT` and `WITHDRAWAL` processing only.

---

## 3. DEPOSIT and WITHDRAWAL Business Definition

A `DEPOSIT` transaction represents external or otherwise eligible inflow of cash into a portfolio cash account.

A `WITHDRAWAL` transaction represents external or otherwise eligible outflow of cash from a portfolio cash account.

A `DEPOSIT` or `WITHDRAWAL` must:

* change cash balances
* be classified as a portfolio-level cash flow
* preserve sufficient information for accounting, performance, reporting, reconciliation, and audit
* remain separable from investment buy/sell activity

A `DEPOSIT` or `WITHDRAWAL` must not:

* change security quantity
* create or consume acquisition lots
* create realized capital P&L
* create realized FX P&L
* be classified as income unless explicitly reclassified under a different transaction type
* be treated as security trades

### 3.1 Non-negotiable semantic invariant

A `DEPOSIT` or `WITHDRAWAL` is a cash movement affecting portfolio cash, not an investment realization or income event. It must change cash, must not change holdings quantity, and must not create realized capital or FX P&L.

### 3.2 Direction rule

* `DEPOSIT` increases cash.
* `WITHDRAWAL` decreases cash.

The direction must be explicit and must not be inferred ambiguously from sign alone.

### 3.3 Portfolio-flow rule

Both `DEPOSIT` and `WITHDRAWAL` must be treated as external portfolio flows by default for performance and funding semantics, unless a customer-specific policy explicitly classifies a subtype differently.

---

## 4. DEPOSIT and WITHDRAWAL Semantic Invariants

The following invariants are mandatory for every valid `DEPOSIT` and `WITHDRAWAL`.

### 4.1 Semantic invariants

* A cash movement must not change security quantity.
* A cash movement must not create or consume lots.
* A `DEPOSIT` must increase eligible cash balances.
* A `WITHDRAWAL` must decrease eligible cash balances.
* A cash movement must be classified as a portfolio flow.
* A cash movement must not create realized capital P&L.
* A cash movement must not create realized FX P&L.
* A cash movement must not be classified as income by default.
* A cash movement must be linkable to the same economic event across all related records.

### 4.2 Numeric invariants

* `cash_amount_local >= 0`
* `cash_amount_base >= 0`
* `net_cash_amount_local >= 0`
* `net_cash_amount_base >= 0`
* `DEPOSIT` increases cash by the configured net amount
* `WITHDRAWAL` decreases cash by the configured net amount
* realized capital P&L local = `0`
* realized FX P&L local = `0`
* realized total P&L local = `0`
* realized capital P&L base = `0`
* realized FX P&L base = `0`
* realized total P&L base = `0`

### 4.3 Linkage invariants

* Every cash movement must have a stable `economic_event_id`.
* Every cash movement must have a stable `linked_transaction_group_id`.
* If linked ledger entries are auto-generated, they must exist.
* If linked external cash records are upstream-provided, the expectation must be explicit and linkable.
* All related records must reconcile to the same economic event.

### 4.4 Audit invariants

* Every derived value must be reproducible from source data, linked data, and policy configuration.
* The active policy id and version must be identifiable for every processed cash movement.
* Source-system identity and traceability must be preserved.

---

## 5. DEPOSIT and WITHDRAWAL Processing Flow

The engine must process a `DEPOSIT` or `WITHDRAWAL` in the following deterministic sequence.

### 5.1 Receive and ingest

The engine must:

* accept a raw cash-movement payload
* classify it as `DEPOSIT` or `WITHDRAWAL`
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
* sufficient-cash rules for withdrawals under active policy

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
* fee-treatment policy
* cash-entry mode
* timing policy
* precision policy
* duplicate/replay policy
* negative-cash / overdraft policy

No material calculation may proceed without an active, identifiable policy.

### 5.5 Calculate

The engine must perform calculations in canonical order:

1. determine gross cash amount
2. determine movement-related fees or deductions
3. determine net cash amount
4. convert relevant amounts to base currency
5. determine cash-balance effect
6. emit explicit zero realized P&L values
7. determine linkage / ledger behavior

### 5.6 Create business effects

The engine must produce:

* cash-balance delta
* portfolio-flow classification
* linked ledger or external reconciliation effect
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

## 6. DEPOSIT and WITHDRAWAL Canonical Data Model

### 6.1 Top-level model

The canonical logical model must be `CashMovementTransaction`.

### 6.2 Required model composition

`CashMovementTransaction` must be composed of:

* `TransactionIdentity`
* `TransactionLifecycle`
* `CashMovementDetails`
* `SettlementDetails`
* `AmountDetails`
* `FeeDetails`
* `FxDetails`
* `ClassificationDetails`
* `CashEffect`
* `RealizedPnlDetails`
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

| Field                         | Type              | Required | Source             | Mutability | Description                                                                   | Sample                   |
| ----------------------------- | ----------------- | -------: | ------------------ | ---------- | ----------------------------------------------------------------------------- | ------------------------ |
| `transaction_id`              | `str`             |      Yes | UPSTREAM / DERIVED | IMMUTABLE  | Unique identifier of this transaction record                                  | `TXN-2026-000523`        |
| `economic_event_id`           | `str`             |      Yes | DERIVED            | IMMUTABLE  | Shared identifier for all linked entries representing the same economic event | `EVT-2026-04987`         |
| `linked_transaction_group_id` | `str`             |      Yes | DERIVED            | IMMUTABLE  | Groups related entries for the same cash movement                             | `LTG-2026-04456`         |
| `transaction_type`            | `TransactionType` |      Yes | UPSTREAM           | IMMUTABLE  | Canonical transaction type enum                                               | `DEPOSIT` / `WITHDRAWAL` |

#### 6.5.2 TransactionLifecycle

| Field               | Type                 | Required | Source                | Mutability | Description                                     | Sample       |
| ------------------- | -------------------- | -------: | --------------------- | ---------- | ----------------------------------------------- | ------------ |
| `effective_date`    | `date`               |      Yes | UPSTREAM              | IMMUTABLE  | Effective business date of the cash movement    | `2026-04-05` |
| `booking_date`      | `date \| None`       |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | Accounting booking date                         | `2026-04-05` |
| `value_date`        | `date \| None`       |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | Value date for ledger purposes                  | `2026-04-05` |
| `settlement_date`   | `date \| None`       |       No | UPSTREAM              | IMMUTABLE  | Settlement date if distinct from effective date | `2026-04-05` |
| `movement_status`   | `CashMovementStatus` |      Yes | UPSTREAM / CONFIGURED | RECOMPUTED | Processing state of the movement                | `BOOKED`     |
| `settlement_status` | `SettlementStatus`   |      Yes | DERIVED / CONFIGURED  | RECOMPUTED | Settlement lifecycle status                     | `COMPLETED`  |

#### 6.5.3 CashMovementDetails

| Field                    | Type                    | Required | Source                | Mutability | Description                              | Sample               |
| ------------------------ | ----------------------- | -------: | --------------------- | ---------- | ---------------------------------------- | -------------------- |
| `portfolio_id`           | `str`                   |      Yes | UPSTREAM              | IMMUTABLE  | Portfolio affected by the cash movement  | `PORT-10001`         |
| `cash_account_id`        | `str`                   |      Yes | UPSTREAM              | IMMUTABLE  | Cash account impacted by the movement    | `CASH-USD-01`        |
| `movement_direction`     | `CashMovementDirection` |      Yes | DERIVED / CONFIGURED  | IMMUTABLE  | Explicit cash movement direction         | `INFLOW` / `OUTFLOW` |
| `movement_reason`        | `CashMovementReason`    |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Business reason for the movement         | `CLIENT_FUNDING`     |
| `counterparty_reference` | `str \| None`           |       No | UPSTREAM              | IMMUTABLE  | External source or destination reference | `BANK-REF-9981`      |

#### 6.5.4 SettlementDetails

| Field                         | Type              | Required | Source                | Mutability | Description                                         | Sample           |
| ----------------------------- | ----------------- | -------: | --------------------- | ---------- | --------------------------------------------------- | ---------------- |
| `cash_effective_timing`       | `EffectiveTiming` |      Yes | CONFIGURED            | IMMUTABLE  | When the cash balance changes for ledger purposes   | `VALUE_DATE`     |
| `performance_cashflow_timing` | `EffectiveTiming` |      Yes | CONFIGURED            | IMMUTABLE  | When performance views recognize the portfolio flow | `EFFECTIVE_DATE` |
| `settlement_currency`         | `str`             |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Currency in which the movement settles              | `USD`            |
| `external_cash_reference`     | `str \| None`     |       No | UPSTREAM              | IMMUTABLE  | External banking/payment reference                  | `PAY-2026-1122`  |

#### 6.5.5 AmountDetails

| Field                     | Type      | Required | Source             | Mutability   | Description                                     | Sample     |
| ------------------------- | --------- | -------: | ------------------ | ------------ | ----------------------------------------------- | ---------- |
| `gross_cash_amount_local` | `Decimal` |      Yes | UPSTREAM / DERIVED | DERIVED_ONCE | Gross movement amount before deductions         | `10000.00` |
| `gross_cash_amount_base`  | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Base-currency equivalent of gross amount        | `10000.00` |
| `net_cash_amount_local`   | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Net amount affecting cash after deductions/fees | `9990.00`  |
| `net_cash_amount_base`    | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Base-currency equivalent of net amount          | `9990.00`  |

#### 6.5.6 FeeDetails

| Field              | Type      | Required | Source   | Mutability   | Description                                  | Sample  |
| ------------------ | --------- | -------: | -------- | ------------ | -------------------------------------------- | ------- |
| `bank_fee_local`   | `Decimal` |      Yes | UPSTREAM | IMMUTABLE    | Banking/payment fee in local currency        | `10.00` |
| `other_fee_local`  | `Decimal` |      Yes | UPSTREAM | IMMUTABLE    | Other movement-related fee in local currency | `0.00`  |
| `total_fees_local` | `Decimal` |      Yes | DERIVED  | DERIVED_ONCE | Sum of all movement-related fees             | `10.00` |
| `total_fees_base`  | `Decimal` |      Yes | DERIVED  | DERIVED_ONCE | Base-currency equivalent of total fees       | `10.00` |

#### 6.5.7 FxDetails

| Field                     | Type          | Required | Source                | Mutability | Description                                     | Sample     |
| ------------------------- | ------------- | -------: | --------------------- | ---------- | ----------------------------------------------- | ---------- |
| `movement_currency`       | `str`         |      Yes | UPSTREAM              | IMMUTABLE  | Currency of the movement                        | `USD`      |
| `portfolio_base_currency` | `str`         |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Portfolio reporting base currency               | `USD`      |
| `movement_fx_rate`        | `Decimal`     |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | FX rate from movement currency to base currency | `1.000000` |
| `fx_rate_source`          | `str \| None` |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | Source of FX rate used                          | `WMR_4PM`  |

#### 6.5.8 ClassificationDetails

| Field                        | Type                        | Required | Source               | Mutability | Description                                         | Sample                                  |
| ---------------------------- | --------------------------- | -------: | -------------------- | ---------- | --------------------------------------------------- | --------------------------------------- |
| `transaction_classification` | `TransactionClassification` |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | High-level classification of the transaction        | `PORTFOLIO_FLOW`                        |
| `cashflow_classification`    | `CashflowClassification`    |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Classification of the cash movement                 | `DEPOSIT_INFLOW` / `WITHDRAWAL_OUTFLOW` |
| `income_classification`      | `IncomeClassification`      |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Income classification applicable to the transaction | `NONE`                                  |

#### 6.5.9 CashEffect

| Field                      | Type      | Required | Source               | Mutability   | Description                                            | Sample                  |
| -------------------------- | --------- | -------: | -------------------- | ------------ | ------------------------------------------------------ | ----------------------- |
| `cash_balance_delta_local` | `Decimal` |      Yes | DERIVED              | DERIVED_ONCE | Cash balance change in local currency                  | `9990.00` or `-9990.00` |
| `cash_balance_delta_base`  | `Decimal` |      Yes | DERIVED              | DERIVED_ONCE | Cash balance change in base currency                   | `9990.00` or `-9990.00` |
| `is_portfolio_flow`        | `bool`    |      Yes | DERIVED / CONFIGURED | IMMUTABLE    | Indicates that this is a portfolio-level external flow | `true`                  |
| `is_position_flow`         | `bool`    |      Yes | DERIVED / CONFIGURED | IMMUTABLE    | Indicates that this is not a position/security flow    | `false`                 |

#### 6.5.10 RealizedPnlDetails

| Field                        | Type      | Required | Source  | Mutability   | Description                            | Sample |
| ---------------------------- | --------- | -------: | ------- | ------------ | -------------------------------------- | ------ |
| `realized_capital_pnl_local` | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized capital P&L in local currency | `0.00` |
| `realized_fx_pnl_local`      | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized FX P&L in local currency      | `0.00` |
| `realized_total_pnl_local`   | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Total realized P&L in local currency   | `0.00` |
| `realized_capital_pnl_base`  | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized capital P&L in base currency  | `0.00` |
| `realized_fx_pnl_base`       | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized FX P&L in base currency       | `0.00` |
| `realized_total_pnl_base`    | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Total realized P&L in base currency    | `0.00` |

#### 6.5.11 LinkageDetails

| Field                        | Type          | Required | Source               | Mutability | Description                                            | Sample                    |
| ---------------------------- | ------------- | -------: | -------------------- | ---------- | ------------------------------------------------------ | ------------------------- |
| `originating_transaction_id` | `str \| None` |       No | LINKED               | IMMUTABLE  | Source transaction for linked entries                  | `TXN-2026-000523`         |
| `link_type`                  | `LinkType`    |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Semantic meaning of the transaction linkage            | `CASH_MOVEMENT_TO_LEDGER` |
| `reconciliation_key`         | `str \| None` |       No | UPSTREAM / DERIVED   | IMMUTABLE  | Key used to reconcile with upstream or banking systems | `RECON-MNO-345`           |

#### 6.5.12 AuditMetadata

| Field                | Type               | Required | Source             | Mutability | Description                             | Sample                 |
| -------------------- | ------------------ | -------: | ------------------ | ---------- | --------------------------------------- | ---------------------- |
| `source_system`      | `str`              |      Yes | UPSTREAM           | IMMUTABLE  | Originating system name                 | `PAYMENTS_PLATFORM`    |
| `external_reference` | `str \| None`      |       No | UPSTREAM           | IMMUTABLE  | Upstream external reference             | `EXT-999333`           |
| `booking_center`     | `str \| None`      |       No | UPSTREAM           | IMMUTABLE  | Booking center / legal booking location | `SGPB`                 |
| `created_at`         | `datetime`         |      Yes | UPSTREAM / DERIVED | IMMUTABLE  | Record creation timestamp               | `2026-04-05T10:00:00Z` |
| `processed_at`       | `datetime \| None` |       No | DERIVED            | RECOMPUTED | Processing completion timestamp         | `2026-04-05T10:00:02Z` |

#### 6.5.13 AdvisoryMetadata

| Field                   | Type          | Required | Source   | Mutability | Description                                          | Sample           |
| ----------------------- | ------------- | -------: | -------- | ---------- | ---------------------------------------------------- | ---------------- |
| `advisor_id`            | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Relationship manager / advisor reference if relevant | `RM-1001`        |
| `client_instruction_id` | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Client instruction reference                         | `CI-2026-7803`   |
| `mandate_reference`     | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Mandate linkage if relevant                          | `DPM-MANDATE-01` |

#### 6.5.14 PolicyMetadata

| Field                        | Type  | Required | Source     | Mutability | Description                                                   | Sample                        |
| ---------------------------- | ----- | -------: | ---------- | ---------- | ------------------------------------------------------------- | ----------------------------- |
| `calculation_policy_id`      | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy identifier used for this calculation                   | `POLICY-CASHMOVE-STD`         |
| `calculation_policy_version` | `str` |      Yes | CONFIGURED | IMMUTABLE  | Version of the calculation policy applied                     | `1.0.0`                       |
| `fee_treatment_policy`       | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy controlling treatment of movement-related fees         | `DEDUCT_FROM_GROSS`           |
| `negative_cash_policy`       | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy controlling withdrawals when cash is insufficient      | `REJECT_IF_INSUFFICIENT_CASH` |
| `cash_generation_policy`     | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy controlling how linked ledger/cash entries are created | `AUTO_GENERATE_LINKED_LEDGER` |

---

## 7. DEPOSIT and WITHDRAWAL Validation Rules

### 7.1 Mandatory required-field validation

A valid cash movement must include, at minimum:

* transaction identity
* transaction type
* effective date
* portfolio identifier
* cash account identifier
* gross amount
* movement currency
* portfolio base currency
* applicable FX rate
* explicit movement direction
* required policy identifiers if not resolved externally

### 7.2 Numeric validation

The engine must enforce:

* `gross_cash_amount_local >= 0`
* all fee amounts `>= 0`
* `movement_fx_rate > 0`
* all numeric fields must be decimal-safe
* all numeric fields must satisfy configured precision rules

### 7.3 Reconciliation validation

If both supplied total amount and derived values are available:

* the engine must reconcile them
* tolerance must be policy-driven
* out-of-tolerance mismatches must fail or park according to policy

### 7.4 Withdrawal sufficiency validation

For `WITHDRAWAL`, the engine must validate under active policy:

* sufficient available cash exists, or
* overdraft / negative-cash usage is explicitly permitted, or
* the movement is parked/rejected according to policy

### 7.5 Enum validation

The engine must validate all enum-constrained fields, including:

* transaction type
* transaction classification
* cashflow classification
* timing values
* movement status
* settlement status
* movement direction
* movement reason
* link type

### 7.6 Referential validation

The engine must validate, where required:

* portfolio reference exists
* cash account reference exists
* linked transaction identifiers are valid when separate ledger/cash mode is used

### 7.7 Validation outcomes

Each validation failure must resolve to one of:

* `HARD_REJECT`
* `PARK_PENDING_REMEDIATION`
* `ACCEPT_WITH_WARNING`
* `RETRYABLE_FAILURE`
* `TERMINAL_FAILURE`

The applicable outcome must be deterministic and policy-driven.

### 7.8 Cash-movement-specific hard-fail conditions

The following must hard-fail unless explicitly configured otherwise:

* negative gross amount
* missing effective date
* missing portfolio identifier
* missing cash account identifier
* invalid transaction type
* cross-currency movement with missing required FX rate
* negative fee component
* policy conflict affecting a material calculation
* insufficient cash for withdrawal when overdraft is not allowed

---

## 8. DEPOSIT and WITHDRAWAL Calculation Rules and Formulas

### 8.1 Input values

The engine must support calculation from the following normalized inputs:

* gross cash amount
* movement-related fees
* movement currency
* portfolio base currency
* movement FX rate

### 8.2 Derived values

The engine must derive, at minimum:

* `gross_cash_amount_local`
* `gross_cash_amount_base`
* `total_fees_local`
* `total_fees_base`
* `net_cash_amount_local`
* `net_cash_amount_base`
* `cash_balance_delta_local`
* `cash_balance_delta_base`
* explicit realized P&L zero values

### 8.3 Canonical formula order

The engine must calculate in this exact order:

1. determine `gross_cash_amount_local`
2. determine movement-related fees
3. determine `net_cash_amount_local`
4. convert required values into base currency
5. determine cash-balance delta
6. emit explicit zero realized P&L fields
7. determine linkage / ledger behavior

### 8.4 Net cash calculation

By default:

`net_cash_amount_local = gross_cash_amount_local - total_fees_local`

If policy treats fees separately rather than netting them into the movement, the economic event must still remain decomposable and reconcilable.

### 8.5 Base-currency conversion

The engine must convert all relevant local amounts to base currency using the active FX policy.

By default:

`amount_base = amount_local × movement_fx_rate`

### 8.6 Cash-balance delta calculation

For `DEPOSIT` by default:

`cash_balance_delta_local = net_cash_amount_local`

For `WITHDRAWAL` by default:

`cash_balance_delta_local = -net_cash_amount_local`

The same directional rule applies in base currency.

### 8.7 Realized P&L fields

For every `DEPOSIT` and `WITHDRAWAL`, the engine must explicitly produce:

* realized capital P&L local = `0`
* realized FX P&L local = `0`
* realized total P&L local = `0`
* realized capital P&L base = `0`
* realized FX P&L base = `0`
* realized total P&L base = `0`

These fields must be present and must not be omitted.

### 8.8 Rounding and precision

The engine must define:

* internal calculation precision
* rounding scale per amount type
* rounding mode
* presentation scale
* FX conversion rounding rules
* reconciliation tolerance rules

Rounding must be applied only at defined calculation boundaries and must not vary by implementation.

---

## 9. DEPOSIT and WITHDRAWAL Cash Rules

### 9.1 Core cash rule

A cash movement must change cash.

### 9.2 Directional cash rule

* `DEPOSIT` increases cash.
* `WITHDRAWAL` decreases cash.

### 9.3 Required cash concepts

The engine must support:

* gross movement amount
* movement-related fees
* net movement amount
* resulting cash-balance delta

### 9.4 Cash balance views

The platform must distinguish, where relevant:

* available cash
* settled cash
* projected cash
* ledger cash

### 9.5 Balance application rule

The movement must update the correct cash view(s) according to active timing policy.

### 9.6 Cash invariants

* A cash movement must always be linked or explicitly externally expected.
* Duplicate ledger/cash creation must be prevented.
* All related records must reconcile to the same economic event.

---

## 10. DEPOSIT and WITHDRAWAL Timing Rules

### 10.1 Timing dimensions

The engine must support these timing dimensions independently:

* cash timing
* performance timing
* reporting timing

### 10.2 Supported timing values

Supported values must include:

* `EFFECTIVE_DATE`
* `VALUE_DATE`
* `BOOKING_DATE`
* `SETTLEMENT_DATE`

### 10.3 Cash timing

The system must support cash recognition on the configured effective date, value date, booking date, or settlement date.

### 10.4 Performance timing

The system must support performance recognition of portfolio flows under the configured performance timing policy.

### 10.5 Timing invariants

* Timing behavior must be policy-driven, explicit, and auditable.
* Different timing modes must not silently distort cash, performance, and reporting views.

---

## 11. DEPOSIT and WITHDRAWAL Query / Output Contract

### 11.1 Required query surfaces

After successful processing, the platform must expose:

* enriched transaction view
* cash-balance effect view
* linkage / reconciliation view
* audit view

### 11.2 Required transaction output fields

At minimum, downstream consumers must be able to retrieve:

* canonical transaction identifiers
* core business fields
* gross/net/fee decomposition
* classification fields
* timing fields
* policy metadata
* explicit realized P&L structure
* linkage fields

### 11.3 Required cash output fields

At minimum:

* cash account id
* gross amount local/base
* net amount local/base
* cash-balance delta local/base
* portfolio-flow indicators

### 11.4 Consistency expectation

The platform must define whether these surfaces are:

* synchronous
* eventually consistent

and must document the expected latency/SLA for visibility.

---

## 12. DEPOSIT and WITHDRAWAL Worked Examples

### 12.1 Example A: Deposit with bank fee

#### Inputs

* transaction type: `DEPOSIT`
* gross cash amount local: `10000.00`
* bank fee local: `10.00`
* other fees local: `0.00`
* movement currency: `USD`
* base currency: `USD`
* FX rate: `1.000000`

#### Derivations

* `total_fees_local = 10.00`
* `net_cash_amount_local = 10000.00 - 10.00 = 9990.00`
* `cash_balance_delta_local = 9990.00`
* base equivalents are identical
* realized P&L fields = `0.00`

#### Expected outputs

* cash increases by `9990.00`
* transaction classified as portfolio flow
* no quantity change
* no lot activity

---

### 12.2 Example B: Withdrawal with no fee

#### Inputs

* transaction type: `WITHDRAWAL`
* gross cash amount local: `2500.00`
* total fees local: `0.00`

#### Derivations

* `net_cash_amount_local = 2500.00`
* `cash_balance_delta_local = -2500.00`

#### Expected outputs

* cash decreases by `2500.00`
* transaction classified as portfolio flow
* no quantity change
* no lot activity

---

### 12.3 Example C: Cross-currency deposit

#### Inputs

* transaction type: `DEPOSIT`
* gross cash amount local: `10000.00 USD`
* total fees local: `10.00 USD`
* movement FX rate: `1.350000`
* base currency: `SGD`

#### Derivations

* `net_cash_amount_local = 9990.00`
* `gross_cash_amount_base = 13500.00`
* `net_cash_amount_base = 9990.00 × 1.35 = 13486.50`
* `cash_balance_delta_base = 13486.50`

#### Expected outputs

* local and base cash effects populated
* no realized FX P&L
* FX conversion remains explicit and traceable

---

### 12.4 Example D: Withdrawal rejected for insufficient cash

#### Inputs

* transaction type: `WITHDRAWAL`
* requested amount: `5000.00`
* available cash: `3000.00`
* negative-cash policy: `REJECT_IF_INSUFFICIENT_CASH`

#### Expected outputs

* validation or policy failure
* no cash movement posted
* explicit failure reason code
* transaction rejected or parked according to policy

---

## 13. DEPOSIT and WITHDRAWAL Decision Tables

### 13.1 Direction decision table

| Condition    | Required behavior |
| ------------ | ----------------- |
| `DEPOSIT`    | Increase cash     |
| `WITHDRAWAL` | Decrease cash     |

### 13.2 Fee treatment decision table

| Condition                | Required behavior                                                    |
| ------------------------ | -------------------------------------------------------------------- |
| Fees deducted from gross | Net amount = gross - fees                                            |
| Fees booked separately   | Net amount and fee effect remain separately visible and reconcilable |
| No fees                  | Net amount = gross                                                   |

### 13.3 Withdrawal sufficiency decision table

| Condition                                   | Required behavior                     |
| ------------------------------------------- | ------------------------------------- |
| Sufficient cash available                   | Process withdrawal                    |
| Insufficient cash and overdraft allowed     | Process according to overdraft policy |
| Insufficient cash and overdraft not allowed | Reject or park                        |

### 13.4 Timing decision table

| Condition                                 | Required behavior               |
| ----------------------------------------- | ------------------------------- |
| `cash_effective_timing = EFFECTIVE_DATE`  | Cash updated on effective date  |
| `cash_effective_timing = VALUE_DATE`      | Cash updated on value date      |
| `cash_effective_timing = BOOKING_DATE`    | Cash updated on booking date    |
| `cash_effective_timing = SETTLEMENT_DATE` | Cash updated on settlement date |

---

## 14. DEPOSIT and WITHDRAWAL Test Matrix

The implementation is not complete unless the following test categories are covered.

### 14.1 Validation tests

* accept valid standard `DEPOSIT`
* accept valid standard `WITHDRAWAL`
* reject negative gross amount
* reject negative fee
* reject missing effective date
* reject missing portfolio identifier
* reject missing cash account
* reject invalid enum values
* reject gross/net mismatch beyond tolerance
* reject policy conflicts
* reject insufficient-cash withdrawal when not allowed

### 14.2 Calculation tests

* deposit with fee
* deposit without fee
* withdrawal with fee
* withdrawal without fee
* cross-currency deposit
* cross-currency withdrawal
* explicit zero realized P&L fields

### 14.3 Cash tests

* deposit increases cash
* withdrawal decreases cash
* correct cash-balance delta in local and base currency
* correct portfolio-flow flags
* correct timing application across supported timing modes

### 14.4 Query tests

* enriched transaction visibility
* cash-balance effect visibility
* linkage visibility
* policy metadata visibility

### 14.5 Idempotency and replay tests

* same transaction replay does not duplicate business effects
* duplicate cash-movement detection
* duplicate linked ledger prevention
* replay-safe regeneration of derived state

### 14.6 Failure-mode tests

* validation hard-fail
* park pending remediation
* retryable processing failure
* terminal processing failure
* partial processing with explicit state visibility

---

## 15. DEPOSIT and WITHDRAWAL Edge Cases and Failure Cases

### 15.1 Edge cases

The engine must explicitly handle:

* zero gross amount where allowed by policy
* zero fees
* cross-currency movement without required FX
* supplied gross/net mismatch
* deposit with late linked ledger entry
* withdrawal with late linked ledger entry
* cash movement replay / duplicate arrival
* net amount equals zero due to full fee offset

### 15.2 Failure cases

The engine must explicitly define behavior for:

* validation failure
* referential integrity failure
* policy-resolution failure
* reconciliation failure
* duplicate detection conflict
* insufficient-cash failure
* linked ledger missing beyond expected SLA
* event publish failure after local persistence
* query-read-model lag or partial propagation

### 15.3 Failure semantics requirement

For each failure class, the system must define:

* status
* reason code
* whether retriable
* whether blocking
* whether user-visible
* what operational action is required

---

## 16. DEPOSIT and WITHDRAWAL Configurable Policies

All material cash-movement behavior must be configurable through versioned policy, not code forks.

### 16.1 Mandatory configurable dimensions

The following must be configurable:

* fee treatment
* precision rules
* FX precision
* reconciliation tolerance
* cash-entry / linked-ledger mode
* cash timing
* performance timing
* linkage enforcement
* duplicate/replay handling
* negative-cash / overdraft handling
* strictness of withdrawal sufficiency validation

### 16.2 Policy traceability

Every processed `DEPOSIT` and `WITHDRAWAL` must preserve:

* `calculation_policy_id`
* `calculation_policy_version`

### 16.3 Policy conflict rule

If two policies or policy fragments conflict in a way that changes a material outcome, the engine must not silently choose one. It must fail or park according to policy-resolution rules.

---

## 17. DEPOSIT and WITHDRAWAL Gap Assessment Checklist

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

### 17.1 Characterization rule

If the current implementation already matches a requirement in this RFC, that behavior must be locked with characterization tests before refactoring or enhancement.

### 17.2 Completion rule

`DEPOSIT` and `WITHDRAWAL` are complete only when:

* the full input contract is implemented
* all mandatory validations are enforced
* all mandatory calculations are implemented
* cash-balance direction support is implemented
* timing behavior is implemented
* all required metadata is preserved
* all required query outputs are available
* invariants are enforced
* the required test matrix is complete
* all remaining gaps are explicitly documented and approved

---

## 18. Appendices

### Appendix A: Error and Reason Codes

The platform must maintain a supporting catalog for:

* validation errors
* reconciliation mismatches
* policy-resolution failures
* linkage failures
* duplicate/replay conflicts
* insufficient-cash failures
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

Subsequent transaction RFCs must follow the same structural pattern as this cash-movement RFC to ensure consistency across:

* engineering implementation
* AI-assisted coding
* QA and regression
* BA analysis
* support and ops runbooks
* audit and reconciliation

---

## 19. Final Authoritative Statement

This RFC is the canonical specification for `DEPOSIT` and `WITHDRAWAL`.

If an implementation, test, support workflow, or downstream consumer behavior conflicts with this document, this document is the source of truth unless an approved exception or superseding RFC version explicitly states otherwise.
