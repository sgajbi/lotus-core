# RFC-CHARGE-01 Canonical FEE and TAX Transaction Specification

## 1. Document Metadata

* **Document ID:** RFC-CHARGE-01
* **Title:** Canonical FEE and TAX Transaction Specification
* **Version:** 1.0.0
* **Status:** Draft
* **Owner:** *TBD*
* **Reviewers:** *TBD*
* **Approvers:** *TBD*
* **Last Updated:** *TBD*
* **Effective Date:** *TBD*

### 1.1 Change Log

| Version | Date  | Author | Summary                                     |
| ------- | ----- | ------ | ------------------------------------------- |
| 1.0.0   | *TBD* | *TBD*  | Initial canonical FEE and TAX specification |

### 1.2 Purpose

This document defines the canonical, target-state specification for processing `FEE` and `TAX` transactions in a private-banking / wealth-tech platform.

This RFC is the source of truth for:

* business semantics
* implementation behavior
* AI-assisted code generation
* automated testing
* validation and regression control
* BA analysis
* operations and support runbooks
* reconciliation and audit

Any implementation of `FEE` or `TAX` must conform to this specification unless an approved exception is explicitly documented.

### 1.3 Scope

This RFC applies to all standalone booked fee and tax charges or refunds, including but not limited to:

* custody fees
* advisory fees
* management fees
* performance fees
* brokerage or platform fees booked separately from trades
* account maintenance fees
* service charges
* withholding-tax true-ups booked as standalone tax entries
* transaction taxes booked separately from underlying activity
* stamp duty or levy booked as standalone entries
* tax refunds / fee rebates when represented using the same model with explicit direction

This RFC covers:

* input contract
* validation
* enrichment
* policy resolution
* calculation
* expense / tax recognition
* cash impact
* timing semantics
* linkage semantics
* query visibility
* observability
* test requirements

### 1.4 Out of Scope

This RFC does not define:

* trade-side fees already embedded directly in `BUY` or `SELL` unless posted separately
* dividend or interest withholding embedded directly in those transaction types unless posted separately
* corporate action tax treatments outside standalone charge posting
* cancel / correct / rebook flows
* external payment-network or tax-authority message formats beyond required integration fields

Where out-of-scope processes interact with `FEE` or `TAX`, only the required interfaces, identifiers, and linkage expectations are defined here.

---

## 2. Referenced Shared Standards

This RFC must be read together with the shared transaction-processing standards in the repository.

### 2.1 Foundational shared standards

The following shared documents are normative for `FEE` and `TAX` unless explicitly overridden here:

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

This RFC defines all `FEE`- and `TAX`-specific behavior.

If a shared document defines a generic rule and this RFC defines a charge-specific specialization, the rule in this RFC takes precedence for `FEE` and `TAX` processing only.

---

## 3. FEE and TAX Business Definition

A `FEE` transaction represents a standalone charge or rebate associated with servicing, advice, custody, execution support, administration, or platform usage.

A `TAX` transaction represents a standalone tax charge, levy, duty, withholding adjustment, or tax refund booked independently of the originating economic event.

A `FEE` or `TAX` must:

* recognize an expense, liability settlement, reimbursement, or refund
* create or link a corresponding cash movement unless explicitly accrued-only by policy
* preserve sufficient information for accounting, reporting, reconciliation, and audit
* remain separable from trade, income, and transfer activity

A `FEE` or `TAX` must not:

* change security quantity
* create or consume acquisition lots
* create realized capital P&L
* create realized FX P&L
* be treated as income by default
* be ambiguously merged into unrelated transaction flows when booked standalone

### 3.1 Non-negotiable semantic invariant

A `FEE` or `TAX` is a standalone charge or refund event. By default, it changes cash and/or accrual balances, recognizes an expense or refund effect, and must not change quantity, lot state, or realized capital/FX P&L.

### 3.2 Direction rule

`FEE` and `TAX` must support both:

* **charge/outflow**: decreases cash or increases payable/accrual liability
* **refund/rebate/inflow**: increases cash or decreases payable/accrual liability

The direction must be explicit and must not be inferred ambiguously from sign alone.

### 3.3 Charge classification rule

The engine must distinguish at minimum between:

* fee charges
* fee refunds/rebates
* tax charges
* tax refunds/reclaims

This distinction must remain visible in reporting and audit outputs.

---

## 4. FEE and TAX Semantic Invariants

The following invariants are mandatory for every valid `FEE` and `TAX`.

### 4.1 Semantic invariants

* A charge transaction must not change security quantity.
* A charge transaction must not create or consume lots.
* A charge transaction must recognize an expense/refund or tax/refund effect explicitly.
* A charge transaction must create settlement cash outflow/inflow or explicit accrual-only state under policy.
* A charge transaction must not create realized capital P&L.
* A charge transaction must not create realized FX P&L.
* A charge transaction must not be classified as investment buy/sell activity.
* A charge transaction must be linkable to the originating economic event where relevant.

### 4.2 Numeric invariants

* `gross_charge_local >= 0`
* `gross_charge_base >= 0`
* `net_charge_local >= 0`
* `net_charge_base >= 0`
* realized capital P&L local = `0`
* realized FX P&L local = `0`
* realized total P&L local = `0`
* realized capital P&L base = `0`
* realized FX P&L base = `0`
* realized total P&L base = `0`

### 4.3 Linkage invariants

* Every charge transaction must have a stable `economic_event_id`.
* Every charge transaction must have a stable `linked_transaction_group_id`.
* If cash is auto-generated, the linked cash entry must exist.
* If cash is upstream-provided, the external cash expectation must be explicit and linkable.
* Charge-side and cash-side effects must be reconcilable to the same economic event.

### 4.4 Audit invariants

* Every derived value must be reproducible from source data, linked data, and policy configuration.
* The active policy id and version must be identifiable for every processed charge.
* Source-system identity and traceability must be preserved.

---

## 5. FEE and TAX Processing Flow

The engine must process a `FEE` or `TAX` in the following deterministic sequence.

### 5.1 Receive and ingest

The engine must:

* accept a raw charge payload
* classify it as `FEE` or `TAX`
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
* charge-recognition policy
* accrual-vs-cash policy
* cash-entry mode
* timing policy
* precision policy
* duplicate/replay policy

No material calculation may proceed without an active, identifiable policy.

### 5.5 Calculate

The engine must perform calculations in canonical order:

1. determine gross charge amount
2. determine any offsets, rebates, or related subcomponents
3. determine net charge amount
4. convert relevant amounts to base currency
5. determine expense/tax recognition effect
6. determine cash or accrual effect
7. emit explicit zero realized P&L values
8. determine linkage behavior

### 5.6 Create business effects

The engine must produce:

* fee/tax recognition effect
* cashflow effect or accrual-only state
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

## 6. FEE and TAX Canonical Data Model

### 6.1 Top-level model

The canonical logical model must be `ChargeTransaction`.

### 6.2 Required model composition

`ChargeTransaction` must be composed of:

* `TransactionIdentity`
* `TransactionLifecycle`
* `ChargeDetails`
* `SettlementDetails`
* `AmountDetails`
* `FxDetails`
* `ClassificationDetails`
* `PositionEffect`
* `ChargeEffect`
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
| `transaction_id`              | `str`             |      Yes | UPSTREAM / DERIVED | IMMUTABLE  | Unique identifier of this transaction record                                  | `TXN-2026-000723` |
| `economic_event_id`           | `str`             |      Yes | DERIVED            | IMMUTABLE  | Shared identifier for all linked entries representing the same economic event | `EVT-2026-06987`  |
| `linked_transaction_group_id` | `str`             |      Yes | DERIVED            | IMMUTABLE  | Groups related entries for the same charge event                              | `LTG-2026-06456`  |
| `transaction_type`            | `TransactionType` |      Yes | UPSTREAM           | IMMUTABLE  | Canonical transaction type enum                                               | `FEE` / `TAX`     |

#### 6.5.2 TransactionLifecycle

| Field               | Type               | Required | Source                | Mutability | Description                                     | Sample       |
| ------------------- | ------------------ | -------: | --------------------- | ---------- | ----------------------------------------------- | ------------ |
| `effective_date`    | `date`             |      Yes | UPSTREAM              | IMMUTABLE  | Effective business date of the charge           | `2026-04-15` |
| `booking_date`      | `date \| None`     |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | Accounting booking date                         | `2026-04-15` |
| `value_date`        | `date \| None`     |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | Value date for ledger purposes                  | `2026-04-15` |
| `settlement_date`   | `date \| None`     |       No | UPSTREAM              | IMMUTABLE  | Settlement date if distinct from effective date | `2026-04-16` |
| `charge_status`     | `ChargeStatus`     |      Yes | UPSTREAM / CONFIGURED | RECOMPUTED | Processing state of the charge                  | `BOOKED`     |
| `settlement_status` | `SettlementStatus` |      Yes | DERIVED / CONFIGURED  | RECOMPUTED | Settlement lifecycle status                     | `PENDING`    |

#### 6.5.3 ChargeDetails

| Field                   | Type              | Required | Source                | Mutability | Description                                       | Sample                       |
| ----------------------- | ----------------- | -------: | --------------------- | ---------- | ------------------------------------------------- | ---------------------------- |
| `portfolio_id`          | `str`             |      Yes | UPSTREAM              | IMMUTABLE  | Portfolio affected by the charge                  | `PORT-10001`                 |
| `cash_account_id`       | `str \| None`     |       No | UPSTREAM              | IMMUTABLE  | Cash account impacted if settled in cash          | `CASH-USD-01`                |
| `charge_type`           | `ChargeType`      |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Specific category of fee or tax                   | `CUSTODY_FEE` / `STAMP_DUTY` |
| `charge_direction`      | `ChargeDirection` |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Whether the charge is an outflow or refund/inflow | `OUTFLOW`                    |
| `charge_reason`         | `ChargeReason`    |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Business reason for the charge                    | `MONTHLY_CUSTODY_BILLING`    |
| `originating_reference` | `str \| None`     |       No | UPSTREAM              | IMMUTABLE  | Reference to related originating activity if any  | `SELL-REF-2026-0021`         |

#### 6.5.4 SettlementDetails

| Field                   | Type              | Required | Source                | Mutability | Description                                                          | Sample           |
| ----------------------- | ----------------- | -------: | --------------------- | ---------- | -------------------------------------------------------------------- | ---------------- |
| `cash_effective_timing` | `EffectiveTiming` |      Yes | CONFIGURED            | IMMUTABLE  | When cash changes for ledger purposes                                | `VALUE_DATE`     |
| `recognition_timing`    | `EffectiveTiming` |      Yes | CONFIGURED            | IMMUTABLE  | When expense/tax is recognized                                       | `EFFECTIVE_DATE` |
| `settlement_currency`   | `str`             |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Currency in which the charge is settled                              | `USD`            |
| `accrual_only`          | `bool`            |      Yes | CONFIGURED            | IMMUTABLE  | Whether the charge is accrual-only with no immediate cash settlement | `false`          |

#### 6.5.5 AmountDetails

| Field                 | Type      | Required | Source             | Mutability   | Description                                          | Sample  |
| --------------------- | --------- | -------: | ------------------ | ------------ | ---------------------------------------------------- | ------- |
| `gross_charge_local`  | `Decimal` |      Yes | UPSTREAM / DERIVED | DERIVED_ONCE | Gross charge amount before offsets/rebates           | `25.00` |
| `gross_charge_base`   | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Base-currency equivalent of gross charge             | `25.00` |
| `offset_amount_local` | `Decimal` |      Yes | UPSTREAM / DERIVED | DERIVED_ONCE | Offset, rebate, or credit applied against the charge | `0.00`  |
| `offset_amount_base`  | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Base-currency equivalent of offset                   | `0.00`  |
| `net_charge_local`    | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Net amount recognized and/or settled                 | `25.00` |
| `net_charge_base`     | `Decimal` |      Yes | DERIVED            | DERIVED_ONCE | Base-currency equivalent of net charge               | `25.00` |

#### 6.5.6 FxDetails

| Field                     | Type          | Required | Source                | Mutability | Description                                   | Sample     |
| ------------------------- | ------------- | -------: | --------------------- | ---------- | --------------------------------------------- | ---------- |
| `charge_currency`         | `str`         |      Yes | UPSTREAM              | IMMUTABLE  | Currency of the charge                        | `USD`      |
| `portfolio_base_currency` | `str`         |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Portfolio reporting base currency             | `USD`      |
| `charge_fx_rate`          | `Decimal`     |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | FX rate from charge currency to base currency | `1.000000` |
| `fx_rate_source`          | `str \| None` |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | Source of FX rate used                        | `WMR_4PM`  |

#### 6.5.7 ClassificationDetails

| Field                        | Type                        | Required | Source               | Mutability | Description                                         | Sample                                                                            |
| ---------------------------- | --------------------------- | -------: | -------------------- | ---------- | --------------------------------------------------- | --------------------------------------------------------------------------------- |
| `transaction_classification` | `TransactionClassification` |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | High-level classification of the transaction        | `EXPENSE` / `TAX`                                                                 |
| `cashflow_classification`    | `CashflowClassification`    |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Classification of the cash movement                 | `FEE_OUTFLOW`, `TAX_OUTFLOW`, `FEE_REFUND_INFLOW`, `TAX_REFUND_INFLOW`, or `NONE` |
| `income_classification`      | `IncomeClassification`      |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Income classification applicable to the transaction | `NONE`                                                                            |

#### 6.5.8 PositionEffect

| Field                     | Type      | Required | Source  | Mutability   | Description                          | Sample |
| ------------------------- | --------- | -------: | ------- | ------------ | ------------------------------------ | ------ |
| `position_quantity_delta` | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Quantity change caused by the charge | `0`    |
| `cost_basis_delta_local`  | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Cost-basis change in local currency  | `0.00` |
| `cost_basis_delta_base`   | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Cost-basis change in base currency   | `0.00` |

#### 6.5.9 ChargeEffect

| Field                      | Type      | Required | Source  | Mutability   | Description                                   | Sample                        |
| -------------------------- | --------- | -------: | ------- | ------------ | --------------------------------------------- | ----------------------------- |
| `recognized_charge_local`  | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Charge recognized as expense/tax/refund       | `25.00`                       |
| `recognized_charge_base`   | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Base-currency equivalent of recognized charge | `25.00`                       |
| `cash_balance_delta_local` | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Cash movement caused by the charge            | `-25.00` or `25.00` or `0.00` |
| `cash_balance_delta_base`  | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Base-currency equivalent of cash movement     | `-25.00` or `25.00` or `0.00` |

#### 6.5.10 RealizedPnlDetails

| Field                        | Type      | Required | Source  | Mutability   | Description                            | Sample |
| ---------------------------- | --------- | -------: | ------- | ------------ | -------------------------------------- | ------ |
| `realized_capital_pnl_local` | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized capital P&L in local currency | `0.00` |
| `realized_fx_pnl_local`      | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized FX P&L in local currency      | `0.00` |
| `realized_total_pnl_local`   | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Total realized P&L in local currency   | `0.00` |
| `realized_capital_pnl_base`  | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized capital P&L in base currency  | `0.00` |
| `realized_fx_pnl_base`       | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized FX P&L in base currency       | `0.00` |
| `realized_total_pnl_base`    | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Total realized P&L in base currency    | `0.00` |

#### 6.5.11 CashflowInstruction

| Field                        | Type            | Required | Source               | Mutability | Description                                                      | Sample                 |
| ---------------------------- | --------------- | -------: | -------------------- | ---------- | ---------------------------------------------------------------- | ---------------------- |
| `cash_entry_mode`            | `CashEntryMode` |      Yes | CONFIGURED           | IMMUTABLE  | Whether cash entry is engine-generated or expected from upstream | `AUTO_GENERATE`        |
| `auto_generate_cash_entry`   | `bool`          |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Whether the engine must generate the linked cash entry           | `true`                 |
| `linked_cash_transaction_id` | `str \| None`   |       No | LINKED / DERIVED     | RECOMPUTED | Linked cash transaction identifier                               | `TXN-CASH-2026-000723` |

#### 6.5.12 LinkageDetails

| Field                        | Type          | Required | Source               | Mutability | Description                                                            | Sample                |
| ---------------------------- | ------------- | -------: | -------------------- | ---------- | ---------------------------------------------------------------------- | --------------------- |
| `originating_transaction_id` | `str \| None` |       No | LINKED               | IMMUTABLE  | Related source transaction if the charge is linked to another activity | `TXN-SELL-2026-00021` |
| `link_type`                  | `LinkType`    |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Semantic meaning of the charge linkage                                 | `CHARGE_TO_CASH`      |
| `reconciliation_key`         | `str \| None` |       No | UPSTREAM / DERIVED   | IMMUTABLE  | Key used to reconcile with upstream billing/tax systems                | `RECON-STU-901`       |

#### 6.5.13 AuditMetadata

| Field                | Type               | Required | Source             | Mutability | Description                             | Sample                 |
| -------------------- | ------------------ | -------: | ------------------ | ---------- | --------------------------------------- | ---------------------- |
| `source_system`      | `str`              |      Yes | UPSTREAM           | IMMUTABLE  | Originating system name                 | `BILLING_ENGINE`       |
| `external_reference` | `str \| None`      |       No | UPSTREAM           | IMMUTABLE  | Upstream external reference             | `EXT-999555`           |
| `booking_center`     | `str \| None`      |       No | UPSTREAM           | IMMUTABLE  | Booking center / legal booking location | `SGPB`                 |
| `created_at`         | `datetime`         |      Yes | UPSTREAM / DERIVED | IMMUTABLE  | Record creation timestamp               | `2026-04-15T14:00:00Z` |
| `processed_at`       | `datetime \| None` |       No | DERIVED            | RECOMPUTED | Processing completion timestamp         | `2026-04-15T14:00:02Z` |

#### 6.5.14 AdvisoryMetadata

| Field                   | Type          | Required | Source   | Mutability | Description                                          | Sample           |
| ----------------------- | ------------- | -------: | -------- | ---------- | ---------------------------------------------------- | ---------------- |
| `advisor_id`            | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Relationship manager / advisor reference if relevant | `RM-1001`        |
| `client_instruction_id` | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Client instruction reference if manually triggered   | `CI-2026-7805`   |
| `mandate_reference`     | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Mandate linkage if relevant                          | `DPM-MANDATE-01` |

#### 6.5.15 PolicyMetadata

| Field                        | Type  | Required | Source     | Mutability | Description                                                  | Sample                        |
| ---------------------------- | ----- | -------: | ---------- | ---------- | ------------------------------------------------------------ | ----------------------------- |
| `calculation_policy_id`      | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy identifier used for this calculation                  | `POLICY-CHARGE-STD`           |
| `calculation_policy_version` | `str` |      Yes | CONFIGURED | IMMUTABLE  | Version of the calculation policy applied                    | `1.0.0`                       |
| `recognition_policy`         | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy controlling when/how the charge is recognized         | `RECOGNIZE_ON_EFFECTIVE_DATE` |
| `accrual_cash_policy`        | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy controlling accrual-only vs immediate cash settlement | `IMMEDIATE_CASH_SETTLEMENT`   |
| `cash_generation_policy`     | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy controlling how linked cash entries are created       | `AUTO_GENERATE_LINKED_CASH`   |

---

## 7. FEE and TAX Validation Rules

### 7.1 Mandatory required-field validation

A valid charge must include, at minimum:

* transaction identity
* transaction type
* effective date
* portfolio identifier
* charge type
* explicit charge direction
* gross charge amount
* charge currency
* portfolio base currency
* applicable FX rate
* required policy identifiers if not resolved externally

### 7.2 Numeric validation

The engine must enforce:

* `gross_charge_local >= 0`
* `offset_amount_local >= 0`
* `charge_fx_rate > 0`
* all numeric fields must be decimal-safe
* all numeric fields must satisfy configured precision rules

### 7.3 Reconciliation validation

If both supplied total amount and derived component values are available:

* the engine must reconcile them
* tolerance must be policy-driven
* out-of-tolerance mismatches must fail or park according to policy

### 7.4 Enum validation

The engine must validate all enum-constrained fields, including:

* transaction type
* transaction classification
* cashflow classification
* timing values
* charge status
* settlement status
* charge type
* charge direction
* link type

### 7.5 Referential validation

The engine must validate, where required:

* portfolio reference exists
* cash account reference exists when immediate cash settlement applies
* linked transaction identifiers are valid when charge linkage is used

### 7.6 Validation outcomes

Each validation failure must resolve to one of:

* `HARD_REJECT`
* `PARK_PENDING_REMEDIATION`
* `ACCEPT_WITH_WARNING`
* `RETRYABLE_FAILURE`
* `TERMINAL_FAILURE`

The applicable outcome must be deterministic and policy-driven.

### 7.7 Charge-specific hard-fail conditions

The following must hard-fail unless explicitly configured otherwise:

* negative gross charge
* negative offset amount
* missing effective date
* missing portfolio identifier
* invalid transaction type
* missing required FX rate for cross-currency charge
* policy conflict affecting a material calculation
* missing required cash account for immediate cash settlement

---

## 8. FEE and TAX Calculation Rules and Formulas

### 8.1 Input values

The engine must support calculation from the following normalized inputs:

* gross charge amount
* offset / rebate amount
* charge currency
* portfolio base currency
* charge FX rate

### 8.2 Derived values

The engine must derive, at minimum:

* `gross_charge_local`
* `gross_charge_base`
* `offset_amount_local`
* `offset_amount_base`
* `net_charge_local`
* `net_charge_base`
* `recognized_charge_local`
* `recognized_charge_base`
* `cash_balance_delta_local`
* `cash_balance_delta_base`
* explicit zero realized P&L values

### 8.3 Canonical formula order

The engine must calculate in this exact order:

1. determine `gross_charge_local`
2. determine offsets / rebates
3. determine `net_charge_local`
4. convert required values into base currency
5. determine recognition effect
6. determine cash or accrual effect
7. emit explicit zero realized P&L fields
8. determine linkage behavior

### 8.4 Net charge calculation

By default:

`net_charge_local = gross_charge_local - offset_amount_local`

### 8.5 Recognition calculation

By default:

`recognized_charge_local = net_charge_local`

The direction of recognition (expense vs refund) must be determined by `charge_direction` and classification, not by negative amounts.

### 8.6 Cash delta calculation

For `charge_direction = OUTFLOW` with immediate cash settlement:

`cash_balance_delta_local = -net_charge_local`

For `charge_direction = INFLOW` with immediate cash settlement:

`cash_balance_delta_local = +net_charge_local`

For accrual-only postings:

`cash_balance_delta_local = 0`

### 8.7 Base-currency conversion

The engine must convert all relevant local amounts to base currency using the active FX policy.

By default:

`amount_base = amount_local × charge_fx_rate`

### 8.8 Realized P&L fields

For every `FEE` and `TAX`, the engine must explicitly produce:

* realized capital P&L local = `0`
* realized FX P&L local = `0`
* realized total P&L local = `0`
* realized capital P&L base = `0`
* realized FX P&L base = `0`
* realized total P&L base = `0`

These fields must be present and must not be omitted.

### 8.9 Rounding and precision

The engine must define:

* internal calculation precision
* rounding scale per amount type
* rounding mode
* presentation scale
* FX conversion rounding rules
* reconciliation tolerance rules

Rounding must be applied only at defined calculation boundaries and must not vary by implementation.

---

## 9. FEE and TAX Cash Rules

### 9.1 Core cash rule

A charge may create a cash movement, but only when the posting is not accrual-only.

### 9.2 Directional cash rule

* `OUTFLOW` decreases cash.
* `INFLOW` increases cash.

### 9.3 Required cash concepts

The engine must support:

* gross charge amount
* offset / rebate amount
* net charge amount
* resulting cash-balance delta

### 9.4 Accrual-only rule

If `accrual_only = true`:

* the charge must be recognized
* cash must not change immediately
* later settlement must remain linkable and auditable as a separate or linked event

### 9.5 Cash balance views

The platform must distinguish, where relevant:

* available cash
* settled cash
* projected cash
* ledger cash

### 9.6 Cash invariants

* A charge cash effect must always be linked or explicitly externally expected.
* Duplicate cash creation must be prevented.
* Charge-side and cash-side effects must reconcile to the same economic event.

---

## 10. FEE and TAX Timing Rules

### 10.1 Timing dimensions

The engine must support these timing dimensions independently:

* recognition timing
* cash timing
* reporting timing

### 10.2 Supported timing values

Supported values must include:

* `EFFECTIVE_DATE`
* `VALUE_DATE`
* `BOOKING_DATE`
* `SETTLEMENT_DATE`

### 10.3 Recognition timing

The system must support when the charge is recognized under the configured timing policy.

### 10.4 Cash timing

The system must support when cash is affected under the configured timing policy.

### 10.5 Timing invariants

* Timing behavior must be policy-driven, explicit, and auditable.
* Different timing modes must not silently distort expense/tax recognition, cash, and reporting views.

---

## 11. FEE and TAX Query / Output Contract

### 11.1 Required query surfaces

After successful processing, the platform must expose:

* enriched transaction view
* charge recognition view
* cash effect view
* linkage / reconciliation view
* audit view

### 11.2 Required transaction output fields

At minimum, downstream consumers must be able to retrieve:

* canonical transaction identifiers
* core business fields
* gross/net/offset decomposition
* classification fields
* timing fields
* policy metadata
* explicit realized P&L structure
* linkage fields

### 11.3 Required charge output fields

At minimum:

* charge type
* charge direction
* recognized charge local/base
* cash-balance delta local/base
* accrual-only indicator

### 11.4 Consistency expectation

The platform must define whether these surfaces are:

* synchronous
* eventually consistent

and must document the expected latency/SLA for visibility.

---

## 12. FEE and TAX Worked Examples

### 12.1 Example A: Custody fee cash outflow

#### Inputs

* transaction type: `FEE`
* charge type: `CUSTODY_FEE`
* charge direction: `OUTFLOW`
* gross charge local: `25.00`
* offset local: `0.00`
* charge currency: `USD`
* base currency: `USD`
* FX rate: `1.000000`
* accrual_only: `false`

#### Derivations

* `net_charge_local = 25.00`
* `recognized_charge_local = 25.00`
* `cash_balance_delta_local = -25.00`
* base equivalents are identical
* realized P&L fields = `0.00`

#### Expected outputs

* cash decreases by `25.00`
* fee expense recognized
* no quantity change
* no lot activity

---

### 12.2 Example B: Tax outflow

#### Inputs

* transaction type: `TAX`
* charge type: `STAMP_DUTY`
* charge direction: `OUTFLOW`
* gross charge local: `12.50`
* offset local: `0.00`

#### Derivations

* `net_charge_local = 12.50`
* `recognized_charge_local = 12.50`
* `cash_balance_delta_local = -12.50`

#### Expected outputs

* cash decreases by `12.50`
* tax charge recognized
* transaction classified as `TAX`

---

### 12.3 Example C: Fee rebate inflow

#### Inputs

* transaction type: `FEE`
* charge type: `PLATFORM_FEE_REBATE`
* charge direction: `INFLOW`
* gross charge local: `10.00`
* offset local: `0.00`

#### Derivations

* `net_charge_local = 10.00`
* `recognized_charge_local = 10.00`
* `cash_balance_delta_local = +10.00`

#### Expected outputs

* cash increases by `10.00`
* fee refund/rebate recognized
* no realized P&L

---

### 12.4 Example D: Accrual-only tax provision

#### Inputs

* transaction type: `TAX`
* charge type: `ESTIMATED_TAX_PROVISION`
* charge direction: `OUTFLOW`
* gross charge local: `100.00`
* accrual_only: `true`

#### Derivations

* `net_charge_local = 100.00`
* `recognized_charge_local = 100.00`
* `cash_balance_delta_local = 0.00`

#### Expected outputs

* tax provision recognized
* no immediate cash movement
* later settlement must remain linkable

---

### 12.5 Example E: Cross-currency charge

#### Inputs

* gross charge local: `25.00 USD`
* offset local: `5.00 USD`
* charge FX rate: `1.350000`
* base currency: `SGD`

#### Derivations

* `net_charge_local = 20.00`
* `gross_charge_base = 33.75`
* `offset_amount_base = 6.75`
* `net_charge_base = 27.00`

#### Expected outputs

* local and base charge values populated
* no realized FX P&L
* FX conversion remains explicit and traceable

---

## 13. FEE and TAX Decision Tables

### 13.1 Direction decision table

| Condition | Required behavior                                         |
| --------- | --------------------------------------------------------- |
| `OUTFLOW` | Recognize charge and decrease cash if cash-settled        |
| `INFLOW`  | Recognize refund/rebate and increase cash if cash-settled |

### 13.2 Settlement mode decision table

| Condition              | Required behavior                          |
| ---------------------- | ------------------------------------------ |
| `accrual_only = false` | Immediate cash effect per timing policy    |
| `accrual_only = true`  | Recognition only, no immediate cash effect |

### 13.3 Transaction type decision table

| Condition | Required behavior              |
| --------- | ------------------------------ |
| `FEE`     | Classify as fee expense/refund |
| `TAX`     | Classify as tax charge/refund  |

### 13.4 Offset decision table

| Condition            | Required behavior                                           |
| -------------------- | ----------------------------------------------------------- |
| No offset            | Net charge = gross charge                                   |
| Offset present       | Net charge = gross - offset                                 |
| Offset exceeds gross | Reject or park unless an explicit over-credit policy exists |

### 13.5 Timing decision table

| Condition                             | Required behavior                     |
| ------------------------------------- | ------------------------------------- |
| `recognition_timing = EFFECTIVE_DATE` | Charge recognized on effective date   |
| `cash_effective_timing = VALUE_DATE`  | Cash updates on value date            |
| `BOOKING_DATE` chosen                 | Effects occur on booking date         |
| `SETTLEMENT_DATE` chosen              | Cash effect occurs on settlement date |

---

## 14. FEE and TAX Test Matrix

The implementation is not complete unless the following test categories are covered.

### 14.1 Validation tests

* accept valid `FEE`
* accept valid `TAX`
* reject negative gross charge
* reject negative offset
* reject missing effective date
* reject missing portfolio identifier
* reject invalid enum values
* reject gross/net mismatch beyond tolerance
* reject policy conflicts
* reject missing required cash account for immediate settlement

### 14.2 Calculation tests

* fee outflow
* tax outflow
* fee rebate inflow
* tax refund inflow
* accrual-only charge
* cross-currency charge
* offset/rebate applied
* explicit zero realized P&L fields

### 14.3 Cash tests

* cash-settled outflow decreases cash
* cash-settled inflow increases cash
* accrual-only charge produces zero immediate cash delta
* correct cash delta in local and base currency
* correct timing application across supported timing modes

### 14.4 Query tests

* enriched transaction visibility
* charge recognition visibility
* cash effect visibility
* linkage visibility
* policy metadata visibility

### 14.5 Idempotency and replay tests

* same transaction replay does not duplicate business effects
* duplicate charge detection
* duplicate linked cash prevention
* replay-safe regeneration of derived state

### 14.6 Failure-mode tests

* validation hard-fail
* park pending remediation
* retryable processing failure
* terminal processing failure
* partial processing with explicit state visibility

---

## 15. FEE and TAX Edge Cases and Failure Cases

### 15.1 Edge cases

The engine must explicitly handle:

* zero gross charge where allowed by policy
* zero offset
* offset equals gross resulting in zero net charge
* cross-currency charge without required FX
* supplied gross/net mismatch
* accrual-only posting with no settlement date
* fee/tax refund represented as inflow
* charge replay / duplicate arrival

### 15.2 Failure cases

The engine must explicitly define behavior for:

* validation failure
* referential integrity failure
* policy-resolution failure
* reconciliation failure
* duplicate detection conflict
* missing linked cash beyond expected SLA for cash-settled postings
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

## 16. FEE and TAX Configurable Policies

All material charge behavior must be configurable through versioned policy, not code forks.

### 16.1 Mandatory configurable dimensions

The following must be configurable:

* recognition timing
* cash timing
* accrual-only vs immediate settlement
* precision rules
* FX precision
* reconciliation tolerance
* offset handling
* cash-entry mode
* linkage enforcement
* duplicate/replay handling
* strictness of required linked references

### 16.2 Policy traceability

Every processed `FEE` and `TAX` must preserve:

* `calculation_policy_id`
* `calculation_policy_version`

### 16.3 Policy conflict rule

If two policies or policy fragments conflict in a way that changes a material outcome, the engine must not silently choose one. It must fail or park according to policy-resolution rules.

---

## 17. FEE and TAX Gap Assessment Checklist

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

`FEE` and `TAX` are complete only when:

* the full input contract is implemented
* all mandatory validations are enforced
* all mandatory calculations are implemented
* charge direction support is implemented
* accrual-only vs cash-settled behavior is implemented
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

Subsequent transaction RFCs must follow the same structural pattern as this charge RFC to ensure consistency across:

* engineering implementation
* AI-assisted coding
* QA and regression
* BA analysis
* support and ops runbooks
* audit and reconciliation

---

## 19. Final Authoritative Statement

This RFC is the canonical specification for `FEE` and `TAX`.

If an implementation, test, support workflow, or downstream consumer behavior conflicts with this document, this document is the source of truth unless an approved exception or superseding RFC version explicitly states otherwise.
