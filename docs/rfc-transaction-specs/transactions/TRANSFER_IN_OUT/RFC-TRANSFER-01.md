# RFC-TRANSFER-01 Canonical TRANSFER_IN and TRANSFER_OUT Transaction Specification

## 1. Document Metadata

* **Document ID:** RFC-TRANSFER-01
* **Title:** Canonical TRANSFER_IN and TRANSFER_OUT Transaction Specification
* **Version:** 1.0.0
* **Status:** Draft
* **Owner:** *TBD*
* **Reviewers:** *TBD*
* **Approvers:** *TBD*
* **Last Updated:** *TBD*
* **Effective Date:** *TBD*

### 1.1 Change Log

| Version | Date  | Author | Summary                                                      |
| ------- | ----- | ------ | ------------------------------------------------------------ |
| 1.0.0   | *TBD* | *TBD*  | Initial canonical TRANSFER_IN and TRANSFER_OUT specification |

### 1.2 Purpose

This document defines the canonical, target-state specification for processing `TRANSFER_IN` and `TRANSFER_OUT` transactions in a private-banking / wealth-tech platform.

This RFC is the source of truth for:

* business semantics
* implementation behavior
* AI-assisted code generation
* automated testing
* validation and regression control
* BA analysis
* operations and support runbooks
* reconciliation and audit

Any implementation of `TRANSFER_IN` or `TRANSFER_OUT` must conform to this specification unless an approved exception is explicitly documented.

### 1.3 Scope

This RFC applies to all booked non-trade transfers of holdings or cash between portfolios, accounts, custodians, or legal wrappers, including but not limited to:

* security transfers between portfolios
* custody in/out movements
* account migration transfers
* book transfers
* internal omnibus-to-client allocations
* external incoming / outgoing security transfers
* cash-only transfers when classified as transfer rather than deposit/withdrawal
* transfers with or without cost-basis continuity
* transfers with lot preservation or lot restatement

This RFC covers:

* input contract
* validation
* enrichment
* policy resolution
* position and/or cash movement
* lot movement and cost-basis handling
* timing semantics
* linkage semantics
* query visibility
* observability
* test requirements

### 1.4 Out of Scope

This RFC does not define:

* buy/sell trade execution
* FX conversion trades
* corporate actions creating new securities
* cancel / correct / rebook flows
* external settlement messaging protocols beyond required integration fields
* asset servicing events not classified as transfer

Where out-of-scope processes interact with `TRANSFER_IN` or `TRANSFER_OUT`, only the required interfaces, identifiers, and linkage expectations are defined here.

---

## 2. Referenced Shared Standards

This RFC must be read together with the shared transaction-processing standards in the repository.

### 2.1 Foundational shared standards

The following shared documents are normative for `TRANSFER_IN` and `TRANSFER_OUT` unless explicitly overridden here:

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

This RFC defines all `TRANSFER_IN`- and `TRANSFER_OUT`-specific behavior.

If a shared document defines a generic rule and this RFC defines a transfer-specific specialization, the rule in this RFC takes precedence for `TRANSFER_IN` and `TRANSFER_OUT` processing only.

---

## 3. TRANSFER_IN and TRANSFER_OUT Business Definition

A `TRANSFER_IN` transaction represents a non-trade movement of holdings or cash into the target portfolio/account.

A `TRANSFER_OUT` transaction represents a non-trade movement of holdings or cash out of the source portfolio/account.

A transfer must:

* move holdings and/or cash without trade execution
* preserve or restate cost basis according to policy
* preserve or restate lots according to policy
* preserve linkage between the outgoing and incoming sides where both are known
* preserve sufficient information for accounting, reporting, reconciliation, and audit

A transfer must not:

* be treated as a market buy/sell
* create realized capital P&L by default
* create realized FX P&L by default
* create income by default
* silently lose cost-basis continuity when continuity is required by policy

### 3.1 Non-negotiable semantic invariant

A transfer moves ownership, custody, or booking location of an asset or cash balance without market realization. By default, it changes holdings and/or cash, preserves economic continuity, and must not create realized capital or FX P&L unless an approved policy explicitly states otherwise.

### 3.2 Direction rule

* `TRANSFER_IN` increases holdings and/or cash in the receiving context.
* `TRANSFER_OUT` decreases holdings and/or cash in the sending context.

The direction must be explicit and must not be inferred ambiguously from sign alone.

### 3.3 Continuity rule

Transfers must support both:

* **economic continuity**: preserve original cost basis / lot lineage
* **restated continuity**: preserve quantity but rebase or re-document cost basis under controlled policy

The active policy must explicitly define which applies.

---

## 4. TRANSFER_IN and TRANSFER_OUT Semantic Invariants

The following invariants are mandatory for every valid transfer.

### 4.1 Semantic invariants

* A transfer must not be classified as a trade.
* A transfer of securities must change quantity in the receiving/sending context.
* A transfer of cash must change cash in the receiving/sending context.
* A transfer must preserve or restate cost basis explicitly under policy.
* A transfer must preserve or restate lot state explicitly under policy.
* A transfer must not create realized capital P&L by default.
* A transfer must not create realized FX P&L by default.
* A transfer must not create income by default.
* A transfer must be linkable across the transfer pair when both sides are known.

### 4.2 Numeric invariants

* `transfer_quantity >= 0`
* `transfer_cash_amount_local >= 0`
* `transfer_cost_basis_local >= 0`
* `transfer_cost_basis_base >= 0`
* `TRANSFER_IN` quantity/cash deltas are positive
* `TRANSFER_OUT` quantity/cash deltas are negative
* realized capital P&L local = `0` by default
* realized FX P&L local = `0` by default
* realized total P&L local = `0` by default
* realized capital P&L base = `0` by default
* realized FX P&L base = `0` by default
* realized total P&L base = `0` by default

### 4.3 Linkage invariants

* Every transfer must have a stable `economic_event_id`.
* Every transfer must have a stable `linked_transaction_group_id`.
* If both sides are represented in the platform, `TRANSFER_IN` and `TRANSFER_OUT` must be explicitly linkable.
* If only one side is represented, the missing side must be externally referenceable.
* Lot and cost-basis lineage must remain reconcilable through linkage keys.

### 4.4 Audit invariants

* Every derived value must be reproducible from source data, linked data, and policy configuration.
* The active policy id and version must be identifiable for every processed transfer.
* Source-system identity and traceability must be preserved.

---

## 5. TRANSFER_IN and TRANSFER_OUT Processing Flow

The engine must process a transfer in the following deterministic sequence.

### 5.1 Receive and ingest

The engine must:

* accept a raw transfer payload
* classify it as `TRANSFER_IN` or `TRANSFER_OUT`
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
* continuity rules
* sufficient-quantity or sufficient-cash rules for outgoing transfers under policy

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
* continuity policy
* lot-preservation policy
* cost-basis policy
* cash-entry mode
* timing policy
* precision policy
* duplicate/replay policy
* insufficient-balance policy

No material calculation may proceed without an active, identifiable policy.

### 5.5 Calculate

The engine must perform calculations in canonical order:

1. determine transferred quantity and/or cash amount
2. determine lot selection or lot import details
3. determine transferred cost basis
4. determine continuity or restatement behavior
5. convert relevant values to base currency
6. determine position and/or cash deltas
7. determine transferred lot effects
8. emit explicit default zero realized P&L values
9. determine linkage / counterpart behavior

### 5.6 Create business effects

The engine must produce:

* position delta where security transfer applies
* cash delta where cash transfer applies
* lot export/import or reduction/increase effects
* continuity metadata
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

## 6. TRANSFER_IN and TRANSFER_OUT Canonical Data Model

### 6.1 Top-level model

The canonical logical model must be `TransferTransaction`.

### 6.2 Required model composition

`TransferTransaction` must be composed of:

* `TransactionIdentity`
* `TransactionLifecycle`
* `TransferDetails`
* `SettlementDetails`
* `QuantityDetails`
* `AmountDetails`
* `CostBasisDetails`
* `FxDetails`
* `ClassificationDetails`
* `PositionEffect`
* `CashEffect`
* `LotTransferEffect`
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

| Field                         | Type              | Required | Source             | Mutability | Description                                                                   | Sample                         |
| ----------------------------- | ----------------- | -------: | ------------------ | ---------- | ----------------------------------------------------------------------------- | ------------------------------ |
| `transaction_id`              | `str`             |      Yes | UPSTREAM / DERIVED | IMMUTABLE  | Unique identifier of this transaction record                                  | `TXN-2026-000623`              |
| `economic_event_id`           | `str`             |      Yes | DERIVED            | IMMUTABLE  | Shared identifier for all linked records representing the same transfer event | `EVT-2026-05987`               |
| `linked_transaction_group_id` | `str`             |      Yes | DERIVED            | IMMUTABLE  | Groups related transfer records                                               | `LTG-2026-05456`               |
| `transaction_type`            | `TransactionType` |      Yes | UPSTREAM           | IMMUTABLE  | Canonical transaction type enum                                               | `TRANSFER_IN` / `TRANSFER_OUT` |

#### 6.5.2 TransactionLifecycle

| Field               | Type               | Required | Source                | Mutability | Description                                     | Sample       |
| ------------------- | ------------------ | -------: | --------------------- | ---------- | ----------------------------------------------- | ------------ |
| `effective_date`    | `date`             |      Yes | UPSTREAM              | IMMUTABLE  | Effective business date of the transfer         | `2026-04-10` |
| `booking_date`      | `date \| None`     |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | Accounting booking date                         | `2026-04-10` |
| `value_date`        | `date \| None`     |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | Value date for ledger purposes                  | `2026-04-10` |
| `settlement_date`   | `date \| None`     |       No | UPSTREAM              | IMMUTABLE  | Settlement date if distinct from effective date | `2026-04-12` |
| `transfer_status`   | `TransferStatus`   |      Yes | UPSTREAM / CONFIGURED | RECOMPUTED | Processing state of the transfer                | `BOOKED`     |
| `settlement_status` | `SettlementStatus` |      Yes | DERIVED / CONFIGURED  | RECOMPUTED | Settlement lifecycle status                     | `PENDING`    |

#### 6.5.3 TransferDetails

| Field                         | Type                | Required | Source                | Mutability | Description                                      | Sample         |
| ----------------------------- | ------------------- | -------: | --------------------- | ---------- | ------------------------------------------------ | -------------- |
| `portfolio_id`                | `str`               |      Yes | UPSTREAM              | IMMUTABLE  | Portfolio affected by this side of the transfer  | `PORT-10001`   |
| `counterparty_portfolio_id`   | `str \| None`       |       No | UPSTREAM              | IMMUTABLE  | Receiving/sending portfolio if known in-platform | `PORT-20002`   |
| `instrument_id`               | `str \| None`       |       No | UPSTREAM              | IMMUTABLE  | Instrument identifier for security transfer      | `AAPL`         |
| `security_id`                 | `str \| None`       |       No | UPSTREAM              | IMMUTABLE  | Security master identifier                       | `US0378331005` |
| `cash_account_id`             | `str \| None`       |       No | UPSTREAM              | IMMUTABLE  | Cash account for cash transfer                   | `CASH-USD-01`  |
| `transfer_asset_type`         | `TransferAssetType` |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Whether the transfer is SECURITY, CASH, or BOTH  | `SECURITY`     |
| `transfer_reason`             | `TransferReason`    |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Business reason for the transfer                 | `CUSTODY_MOVE` |
| `external_transfer_reference` | `str \| None`       |       No | UPSTREAM              | IMMUTABLE  | External custodian or bank reference             | `TRF-EXT-8831` |

#### 6.5.4 SettlementDetails

| Field                         | Type              | Required | Source                | Mutability | Description                                           | Sample           |
| ----------------------------- | ----------------- | -------: | --------------------- | ---------- | ----------------------------------------------------- | ---------------- |
| `position_effective_timing`   | `EffectiveTiming` |      Yes | CONFIGURED            | IMMUTABLE  | When transferred position becomes effective           | `EFFECTIVE_DATE` |
| `cash_effective_timing`       | `EffectiveTiming` |      Yes | CONFIGURED            | IMMUTABLE  | When transferred cash becomes effective               | `VALUE_DATE`     |
| `performance_cashflow_timing` | `EffectiveTiming` |      Yes | CONFIGURED            | IMMUTABLE  | When performance views recognize transfer cash effect | `EFFECTIVE_DATE` |
| `settlement_currency`         | `str \| None`     |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | Currency in which cash portion settles                | `USD`            |

#### 6.5.5 QuantityDetails

| Field                     | Type      | Required | Source     | Mutability   | Description                            | Sample          |
| ------------------------- | --------- | -------: | ---------- | ------------ | -------------------------------------- | --------------- |
| `transfer_quantity`       | `Decimal` |      Yes | UPSTREAM   | IMMUTABLE    | Quantity moved for security transfer   | `100`           |
| `quantity_precision`      | `int`     |      Yes | CONFIGURED | IMMUTABLE    | Allowed decimal precision for quantity | `6`             |
| `position_quantity_delta` | `Decimal` |      Yes | DERIVED    | DERIVED_ONCE | Quantity change caused by the transfer | `100` or `-100` |

#### 6.5.6 AmountDetails

| Field                        | Type      | Required | Source   | Mutability   | Description                            | Sample                           |
| ---------------------------- | --------- | -------: | -------- | ------------ | -------------------------------------- | -------------------------------- |
| `transfer_cash_amount_local` | `Decimal` |      Yes | UPSTREAM | IMMUTABLE    | Cash moved as part of the transfer     | `0.00`                           |
| `transfer_cash_amount_base`  | `Decimal` |      Yes | DERIVED  | DERIVED_ONCE | Base-currency equivalent of cash moved | `0.00`                           |
| `cash_balance_delta_local`   | `Decimal` |      Yes | DERIVED  | DERIVED_ONCE | Cash balance change in local currency  | `0.00`, `5000.00`, or `-5000.00` |
| `cash_balance_delta_base`    | `Decimal` |      Yes | DERIVED  | DERIVED_ONCE | Cash balance change in base currency   | `0.00`, `5000.00`, or `-5000.00` |

#### 6.5.7 CostBasisDetails

| Field                       | Type             | Required | Source             | Mutability   | Description                                        | Sample                    |
| --------------------------- | ---------------- | -------: | ------------------ | ------------ | -------------------------------------------------- | ------------------------- |
| `transfer_cost_basis_local` | `Decimal`        |      Yes | UPSTREAM / DERIVED | DERIVED_ONCE | Cost basis moved with the transfer                 | `15005.50`                |
| `transfer_cost_basis_base`  | `Decimal`        |      Yes | DERIVED            | DERIVED_ONCE | Base-currency equivalent of transferred cost basis | `15005.50`                |
| `continuity_mode`           | `ContinuityMode` |      Yes | CONFIGURED         | IMMUTABLE    | Whether cost basis is preserved or restated        | `PRESERVE`                |
| `cost_basis_delta_local`    | `Decimal`        |      Yes | DERIVED            | DERIVED_ONCE | Cost-basis change in local currency                | `15005.50` or `-15005.50` |
| `cost_basis_delta_base`     | `Decimal`        |      Yes | DERIVED            | DERIVED_ONCE | Cost-basis change in base currency                 | `15005.50` or `-15005.50` |

#### 6.5.8 FxDetails

| Field                     | Type          | Required | Source                | Mutability | Description                                     | Sample     |
| ------------------------- | ------------- | -------: | --------------------- | ---------- | ----------------------------------------------- | ---------- |
| `transfer_currency`       | `str \| None` |       No | UPSTREAM              | IMMUTABLE  | Currency of the transfer cash/cost values       | `USD`      |
| `portfolio_base_currency` | `str`         |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | Portfolio reporting base currency               | `USD`      |
| `transfer_fx_rate`        | `Decimal`     |      Yes | UPSTREAM / CONFIGURED | IMMUTABLE  | FX rate from transfer currency to base currency | `1.000000` |
| `fx_rate_source`          | `str \| None` |       No | UPSTREAM / CONFIGURED | IMMUTABLE  | Source of FX rate used                          | `WMR_4PM`  |

#### 6.5.9 ClassificationDetails

| Field                        | Type                        | Required | Source               | Mutability | Description                                         | Sample                                           |
| ---------------------------- | --------------------------- | -------: | -------------------- | ---------- | --------------------------------------------------- | ------------------------------------------------ |
| `transaction_classification` | `TransactionClassification` |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | High-level classification of the transaction        | `TRANSFER`                                       |
| `cashflow_classification`    | `CashflowClassification`    |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Classification of any cash movement                 | `TRANSFER_INFLOW`, `TRANSFER_OUTFLOW`, or `NONE` |
| `income_classification`      | `IncomeClassification`      |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Income classification applicable to the transaction | `NONE`                                           |

#### 6.5.10 PositionEffect

| Field               | Type           | Required | Source               | Mutability | Description                                                        | Sample                       |
| ------------------- | -------------- | -------: | -------------------- | ---------- | ------------------------------------------------------------------ | ---------------------------- |
| `held_since_date`   | `date \| None` |      Yes | DERIVED              | RECOMPUTED | Holding-period start date after transfer application               | `2025-11-01`                 |
| `is_position_flow`  | `bool`         |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Indicates security transfer affects positions                      | `true`                       |
| `is_portfolio_flow` | `bool`         |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Indicates cash transfer is an external/internal flow as classified | `false` or `true` per policy |

#### 6.5.11 CashEffect

| Field                    | Type          | Required | Source            | Mutability | Description                                  | Sample        |
| ------------------------ | ------------- | -------: | ----------------- | ---------- | -------------------------------------------- | ------------- |
| `cash_movement_present`  | `bool`        |      Yes | DERIVED           | IMMUTABLE  | Indicates whether cash is moved              | `false`       |
| `cash_account_target_id` | `str \| None` |       No | UPSTREAM / LINKED | IMMUTABLE  | Receiving/sending cash account if applicable | `CASH-USD-02` |

#### 6.5.12 LotTransferEffect

| Field                     | Type              | Required | Source             | Mutability   | Description                                            | Sample             |
| ------------------------- | ----------------- | -------: | ------------------ | ------------ | ------------------------------------------------------ | ------------------ |
| `lot_transfer_mode`       | `LotTransferMode` |      Yes | CONFIGURED         | IMMUTABLE    | Whether lots are preserved, merged, split, or restated | `PRESERVE_LOTS`    |
| `source_lot_ids`          | `list[str]`       |      Yes | UPSTREAM / DERIVED | DERIVED_ONCE | Lots exported or referenced by the transfer            | `["LOT-2025-101"]` |
| `target_lot_ids`          | `list[str]`       |      Yes | DERIVED            | DERIVED_ONCE | Lots created or updated on transfer-in                 | `["LOT-2025-101"]` |
| `lot_open_quantity_delta` | `Decimal`         |      Yes | DERIVED            | DERIVED_ONCE | Net lot quantity change caused by the transfer         | `100` or `-100`    |

#### 6.5.13 RealizedPnlDetails

| Field                        | Type      | Required | Source  | Mutability   | Description                            | Sample |
| ---------------------------- | --------- | -------: | ------- | ------------ | -------------------------------------- | ------ |
| `realized_capital_pnl_local` | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized capital P&L in local currency | `0.00` |
| `realized_fx_pnl_local`      | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized FX P&L in local currency      | `0.00` |
| `realized_total_pnl_local`   | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Total realized P&L in local currency   | `0.00` |
| `realized_capital_pnl_base`  | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized capital P&L in base currency  | `0.00` |
| `realized_fx_pnl_base`       | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Realized FX P&L in base currency       | `0.00` |
| `realized_total_pnl_base`    | `Decimal` |      Yes | DERIVED | DERIVED_ONCE | Total realized P&L in base currency    | `0.00` |

#### 6.5.14 LinkageDetails

| Field                            | Type          | Required | Source               | Mutability | Description                                           | Sample            |
| -------------------------------- | ------------- | -------: | -------------------- | ---------- | ----------------------------------------------------- | ----------------- |
| `paired_transfer_transaction_id` | `str \| None` |       No | LINKED               | IMMUTABLE  | Matching in/out side if known in-platform             | `TXN-2026-000624` |
| `originating_transaction_id`     | `str \| None` |       No | LINKED               | IMMUTABLE  | Source transaction for linked entries                 | `TXN-2026-000623` |
| `link_type`                      | `LinkType`    |      Yes | DERIVED / CONFIGURED | IMMUTABLE  | Semantic meaning of the transfer linkage              | `TRANSFER_PAIR`   |
| `reconciliation_key`             | `str \| None` |       No | UPSTREAM / DERIVED   | IMMUTABLE  | Key used to reconcile with upstream/custodian systems | `RECON-PQR-678`   |

#### 6.5.15 AuditMetadata

| Field                | Type               | Required | Source             | Mutability | Description                             | Sample                 |
| -------------------- | ------------------ | -------: | ------------------ | ---------- | --------------------------------------- | ---------------------- |
| `source_system`      | `str`              |      Yes | UPSTREAM           | IMMUTABLE  | Originating system name                 | `CUSTODY_PLATFORM`     |
| `external_reference` | `str \| None`      |       No | UPSTREAM           | IMMUTABLE  | Upstream external reference             | `EXT-999444`           |
| `booking_center`     | `str \| None`      |       No | UPSTREAM           | IMMUTABLE  | Booking center / legal booking location | `SGPB`                 |
| `created_at`         | `datetime`         |      Yes | UPSTREAM / DERIVED | IMMUTABLE  | Record creation timestamp               | `2026-04-10T12:00:00Z` |
| `processed_at`       | `datetime \| None` |       No | DERIVED            | RECOMPUTED | Processing completion timestamp         | `2026-04-10T12:00:03Z` |

#### 6.5.16 AdvisoryMetadata

| Field                   | Type          | Required | Source   | Mutability | Description                                          | Sample           |
| ----------------------- | ------------- | -------: | -------- | ---------- | ---------------------------------------------------- | ---------------- |
| `advisor_id`            | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Relationship manager / advisor reference if relevant | `RM-1001`        |
| `client_instruction_id` | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Client instruction reference                         | `CI-2026-7804`   |
| `mandate_reference`     | `str \| None` |       No | UPSTREAM | IMMUTABLE  | Mandate linkage if relevant                          | `DPM-MANDATE-01` |

#### 6.5.17 PolicyMetadata

| Field                         | Type  | Required | Source     | Mutability | Description                                                       | Sample                         |
| ----------------------------- | ----- | -------: | ---------- | ---------- | ----------------------------------------------------------------- | ------------------------------ |
| `calculation_policy_id`       | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy identifier used for this calculation                       | `POLICY-TRANSFER-STD`          |
| `calculation_policy_version`  | `str` |      Yes | CONFIGURED | IMMUTABLE  | Version of the calculation policy applied                         | `1.0.0`                        |
| `continuity_policy`           | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy controlling cost-basis continuity                          | `PRESERVE_ORIGINAL_COST_BASIS` |
| `lot_transfer_policy`         | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy controlling lot preservation/restatement                   | `PRESERVE_LOTS_IF_AVAILABLE`   |
| `insufficient_balance_policy` | `str` |      Yes | CONFIGURED | IMMUTABLE  | Policy controlling outgoing transfer when balance is insufficient | `REJECT_IF_INSUFFICIENT`       |

---

## 7. TRANSFER_IN and TRANSFER_OUT Validation Rules

### 7.1 Mandatory required-field validation

A valid transfer must include, at minimum:

* transaction identity
* transaction type
* effective date
* portfolio identifier
* transfer asset type
* explicit movement direction
* required quantity and/or cash amount depending on asset type
* required policy identifiers if not resolved externally

### 7.2 Numeric validation

The engine must enforce:

* `transfer_quantity >= 0`
* `transfer_cash_amount_local >= 0`
* `transfer_cost_basis_local >= 0` when required
* `transfer_fx_rate > 0` when applicable
* all numeric fields must be decimal-safe
* all numeric fields must satisfy configured precision rules

### 7.3 Reconciliation validation

If both supplied total values and derived/restated values are available:

* the engine must reconcile them
* tolerance must be policy-driven
* out-of-tolerance mismatches must fail or park according to policy

### 7.4 Outgoing sufficiency validation

For `TRANSFER_OUT`, the engine must validate under active policy:

* sufficient quantity exists for security transfer, or
* sufficient cash exists for cash transfer, or
* exception/overdraft/negative-balance usage is explicitly permitted, or
* the transfer is rejected/parked according to policy

### 7.5 Continuity validation

The engine must validate, where policy requires:

* lot references are complete and valid
* cost basis is provided or derivable
* transfer pair references reconcile
* continuity metadata is sufficient to preserve lineage

### 7.6 Enum validation

The engine must validate all enum-constrained fields, including:

* transaction type
* transaction classification
* cashflow classification
* transfer status
* settlement status
* transfer asset type
* movement direction
* continuity mode
* lot transfer mode
* link type

### 7.7 Referential validation

The engine must validate, where required:

* portfolio reference exists
* cash account reference exists for cash transfers
* instrument/security reference exists for security transfers
* linked transaction identifiers are valid when transfer pair linkage is used
* lot references are valid when lot preservation is required

### 7.8 Validation outcomes

Each validation failure must resolve to one of:

* `HARD_REJECT`
* `PARK_PENDING_REMEDIATION`
* `ACCEPT_WITH_WARNING`
* `RETRYABLE_FAILURE`
* `TERMINAL_FAILURE`

The applicable outcome must be deterministic and policy-driven.

### 7.9 Transfer-specific hard-fail conditions

The following must hard-fail unless explicitly configured otherwise:

* negative quantity
* negative cash amount
* missing effective date
* missing portfolio identifier
* invalid transaction type
* security transfer missing required instrument/security id
* cash transfer missing required cash account id
* missing required FX rate for cross-currency transfer
* policy conflict affecting a material calculation
* insufficient quantity/cash when exceptions are not allowed
* missing continuity data when continuity is mandatory

---

## 8. TRANSFER_IN and TRANSFER_OUT Calculation Rules and Formulas

### 8.1 Input values

The engine must support calculation from the following normalized inputs:

* transfer quantity
* transfer cash amount
* transfer cost basis
* transfer currency
* portfolio base currency
* transfer FX rate
* source lot references and quantities
* continuity or restatement metadata

### 8.2 Derived values

The engine must derive, at minimum:

* `position_quantity_delta`
* `transfer_cash_amount_base`
* `cash_balance_delta_local`
* `cash_balance_delta_base`
* `transfer_cost_basis_base`
* `cost_basis_delta_local`
* `cost_basis_delta_base`
* transferred lot effects
* explicit default zero realized P&L values

### 8.3 Canonical formula order

The engine must calculate in this exact order:

1. determine quantity and/or cash moved
2. determine transferred cost basis
3. determine continuity or restatement behavior
4. determine lot transfer mapping
5. convert required values into base currency
6. determine position and/or cash deltas
7. determine cost-basis deltas
8. emit explicit default zero realized P&L fields
9. determine linkage behavior

### 8.4 Quantity delta calculation

For security transfers:

* `TRANSFER_IN`: `position_quantity_delta = +transfer_quantity`
* `TRANSFER_OUT`: `position_quantity_delta = -transfer_quantity`

For cash-only transfers:

* `position_quantity_delta = 0`

### 8.5 Cash delta calculation

For cash transfers:

* `TRANSFER_IN`: `cash_balance_delta_local = +transfer_cash_amount_local`
* `TRANSFER_OUT`: `cash_balance_delta_local = -transfer_cash_amount_local`

For security-only transfers:

* `cash_balance_delta_local = 0`

### 8.6 Cost-basis delta calculation

By default under continuity preservation:

* `TRANSFER_IN`: `cost_basis_delta_local = +transfer_cost_basis_local`
* `TRANSFER_OUT`: `cost_basis_delta_local = -transfer_cost_basis_local`

If policy restates cost basis, the transferred basis must still be explicit and auditable.

### 8.7 Base-currency conversion

The engine must convert all relevant local amounts to base currency using the active FX policy.

By default:

`amount_base = amount_local × transfer_fx_rate`

### 8.8 Realized P&L fields

For every transfer, the engine must explicitly produce by default:

* realized capital P&L local = `0`
* realized FX P&L local = `0`
* realized total P&L local = `0`
* realized capital P&L base = `0`
* realized FX P&L base = `0`
* realized total P&L base = `0`

If a customer-specific approved policy allows realization on transfer, that behavior must be explicitly documented and override this default.

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

## 9. TRANSFER_IN and TRANSFER_OUT Position and Lot Rules

### 9.1 Security transfer position rule

A security transfer must change position quantity in the receiving/sending context.

### 9.2 Cash-only transfer position rule

A cash-only transfer must not change security quantity.

### 9.3 Held-since behavior

Under continuity preservation policy:

* `TRANSFER_IN` should preserve original `held_since_date` where available
* `TRANSFER_OUT` should not create a new holding period
* if continuity data is absent and restatement is allowed, held-since behavior must be policy-defined and explicit

### 9.4 Lot preservation rule

Under lot-preservation policy:

* source lots must be exported/referenced
* target lots must preserve lineage, quantity, and cost basis as required

### 9.5 Lot restatement rule

Under lot-restatement policy:

* target lots may be recreated, merged, or split
* the mapping from source to target must remain auditable

### 9.6 Position and lot invariants

* Transfer must not create new economic acquisition or disposal by default.
* Lot continuity or restatement must be explicit.
* Quantity and cost-basis deltas must reconcile to the transferred payload and policy.

---

## 10. TRANSFER_IN and TRANSFER_OUT Cash Rules

### 10.1 Core cash rule

A transfer may move cash, but only when the transfer asset type includes cash.

### 10.2 Directional cash rule

* `TRANSFER_IN` increases cash.
* `TRANSFER_OUT` decreases cash.

### 10.3 Required cash concepts

The engine must support:

* transferred cash amount
* resulting cash-balance delta
* linked receiving/sending cash account when known

### 10.4 Cash balance views

The platform must distinguish, where relevant:

* available cash
* settled cash
* projected cash
* ledger cash

### 10.5 Cash invariants

* Cash transfer effects must always be explicit.
* Duplicate cash creation must be prevented.
* Transfer-side and counterpart-side records must reconcile to the same economic event.

---

## 11. TRANSFER_IN and TRANSFER_OUT Timing Rules

### 11.1 Timing dimensions

The engine must support these timing dimensions independently:

* position timing
* cash timing
* performance timing
* reporting timing

### 11.2 Supported timing values

Supported values must include:

* `EFFECTIVE_DATE`
* `VALUE_DATE`
* `BOOKING_DATE`
* `SETTLEMENT_DATE`

### 11.3 Position timing

The system must support when transferred holdings become visible/effective under the configured timing policy.

### 11.4 Cash timing

The system must support when transferred cash becomes visible/effective under the configured timing policy.

### 11.5 Performance timing

The system must support whether transfer cash should or should not be treated as a portfolio flow in performance calculations, according to policy.

### 11.6 Timing invariants

* Timing behavior must be policy-driven, explicit, and auditable.
* Different timing modes must not silently distort holdings, cash, and reporting views.

---

## 12. TRANSFER_IN and TRANSFER_OUT Query / Output Contract

### 12.1 Required query surfaces

After successful processing, the platform must expose:

* enriched transaction view
* position effect view
* cash effect view
* lot transfer view
* linkage / reconciliation view
* audit view

### 12.2 Required transaction output fields

At minimum, downstream consumers must be able to retrieve:

* canonical transaction identifiers
* core business fields
* quantity/cash/cost-basis decomposition
* continuity and lot-transfer metadata
* classification fields
* timing fields
* policy metadata
* explicit realized P&L structure
* linkage fields

### 12.3 Required holdings output fields

At minimum:

* quantity delta
* cost-basis delta
* held-since outcome
* lot transfer mapping or restatement outcome

### 12.4 Required cash output fields

At minimum:

* cash delta local/base
* cash account references where applicable
* transfer flow indicators

### 12.5 Consistency expectation

The platform must define whether these surfaces are:

* synchronous
* eventually consistent

and must document the expected latency/SLA for visibility.

---

## 13. TRANSFER_IN and TRANSFER_OUT Worked Examples

### 13.1 Example A: Security TRANSFER_IN with preserved cost basis

#### Inputs

* transaction type: `TRANSFER_IN`
* asset type: `SECURITY`
* transfer quantity: `100`
* transfer cost basis local: `15005.50`
* continuity mode: `PRESERVE`
* lot transfer mode: `PRESERVE_LOTS`

#### Derivations

* `position_quantity_delta = +100`
* `cost_basis_delta_local = +15005.50`
* `cash_balance_delta_local = 0`
* realized P&L fields = `0.00`

#### Expected outputs

* position quantity increases by `100`
* cost basis increases by `15005.50`
* source lot lineage is preserved in target context
* no cash movement

---

### 13.2 Example B: Security TRANSFER_OUT with preserved cost basis

#### Inputs

* transaction type: `TRANSFER_OUT`
* asset type: `SECURITY`
* transfer quantity: `100`
* transfer cost basis local: `15005.50`

#### Derivations

* `position_quantity_delta = -100`
* `cost_basis_delta_local = -15005.50`
* `cash_balance_delta_local = 0`

#### Expected outputs

* position quantity decreases by `100`
* cost basis decreases by `15005.50`
* lots are reduced/exported
* no realized P&L

---

### 13.3 Example C: Cash TRANSFER_IN

#### Inputs

* transaction type: `TRANSFER_IN`
* asset type: `CASH`
* transfer cash amount local: `5000.00`
* FX rate: `1.000000`

#### Derivations

* `position_quantity_delta = 0`
* `cash_balance_delta_local = +5000.00`
* `cost_basis_delta_local = 0.00`

#### Expected outputs

* cash increases by `5000.00`
* no security quantity change
* classified per transfer cashflow policy

---

### 13.4 Example D: Cash TRANSFER_OUT rejected for insufficient cash

#### Inputs

* transaction type: `TRANSFER_OUT`
* asset type: `CASH`
* transfer cash amount local: `7000.00`
* available cash: `3000.00`
* insufficient-balance policy: `REJECT_IF_INSUFFICIENT`

#### Expected outputs

* validation or policy failure
* no cash movement posted
* explicit failure reason code
* transaction rejected or parked according to policy

---

### 13.5 Example E: In-platform paired transfer

#### Inputs

* source side `TRANSFER_OUT`
* target side `TRANSFER_IN`
* paired transfer ids known

#### Expected outputs

* both sides share same `economic_event_id`
* each side references the other through pairing linkage
* quantity/cash/cost-basis totals reconcile across the pair

---

## 14. TRANSFER_IN and TRANSFER_OUT Decision Tables

### 14.1 Asset-type decision table

| Condition  | Required behavior                                          |
| ---------- | ---------------------------------------------------------- |
| `SECURITY` | Change quantity and cost basis; manage lots                |
| `CASH`     | Change cash only                                           |
| `BOTH`     | Change quantity, cost basis, and cash according to payload |

### 14.2 Continuity decision table

| Condition                        | Required behavior                                                |
| -------------------------------- | ---------------------------------------------------------------- |
| `PRESERVE`                       | Preserve cost basis and lineage                                  |
| `RESTATE`                        | Restate basis under explicit policy while preserving audit trail |
| Missing required continuity data | Reject or park                                                   |

### 14.3 Lot-transfer decision table

| Condition       | Required behavior                                  |
| --------------- | -------------------------------------------------- |
| `PRESERVE_LOTS` | Preserve source-to-target lot lineage              |
| `MERGE_LOTS`    | Merge into target lots with explicit mapping       |
| `SPLIT_LOTS`    | Split into target lots with explicit mapping       |
| `RESTATE_LOTS`  | Recreate target lots under policy with audit trail |

### 14.4 Sufficiency decision table

| Condition                              | Required behavior           |
| -------------------------------------- | --------------------------- |
| Sufficient quantity/cash available     | Process transfer out        |
| Insufficient and exception allowed     | Process according to policy |
| Insufficient and exception not allowed | Reject or park              |

### 14.5 Timing decision table

| Condition                                    | Required behavior                 |
| -------------------------------------------- | --------------------------------- |
| `position_effective_timing = EFFECTIVE_DATE` | Holdings update on effective date |
| `cash_effective_timing = VALUE_DATE`         | Cash updates on value date        |
| `SETTLEMENT_DATE` chosen                     | Effects occur on settlement date  |
| `BOOKING_DATE` chosen                        | Effects occur on booking date     |

---

## 15. TRANSFER_IN and TRANSFER_OUT Test Matrix

The implementation is not complete unless the following test categories are covered.

### 15.1 Validation tests

* accept valid `TRANSFER_IN`
* accept valid `TRANSFER_OUT`
* reject negative quantity
* reject negative cash amount
* reject missing effective date
* reject missing portfolio identifier
* reject missing required instrument/security for security transfer
* reject missing required cash account for cash transfer
* reject invalid enum values
* reject missing continuity data when mandatory
* reject policy conflicts
* reject insufficient outgoing balance when not allowed

### 15.2 Calculation tests

* security transfer in with preserved basis
* security transfer out with preserved basis
* cash transfer in
* cash transfer out
* mixed asset transfer
* cross-currency transfer
* restated-basis transfer
* explicit default zero realized P&L fields

### 15.3 Position and lot tests

* transfer in increases quantity
* transfer out decreases quantity
* preserved held-since under continuity mode
* preserved lots
* merged lots
* split lots
* restated lots
* cost-basis delta matches transfer basis

### 15.4 Cash tests

* cash transfer in increases cash
* cash transfer out decreases cash
* correct cash delta in local and base currency
* correct timing application across supported timing modes

### 15.5 Pairing and linkage tests

* in-platform paired transfer linkage
* one-sided transfer with external reference only
* duplicate pair prevention
* reconciliation across transfer pair

### 15.6 Query tests

* enriched transaction visibility
* position effect visibility
* cash effect visibility
* lot transfer visibility
* policy metadata visibility

### 15.7 Idempotency and replay tests

* same transaction replay does not duplicate business effects
* duplicate transfer detection
* duplicate pair/link prevention
* replay-safe regeneration of derived state

### 15.8 Failure-mode tests

* validation hard-fail
* park pending remediation
* retryable processing failure
* terminal processing failure
* partial processing with explicit state visibility

---

## 16. TRANSFER_IN and TRANSFER_OUT Edge Cases and Failure Cases

### 16.1 Edge cases

The engine must explicitly handle:

* zero quantity where allowed by policy
* zero cash amount where allowed by policy
* cash-only transfer
* security-only transfer
* mixed asset transfer
* cross-currency transfer without required FX
* transfer with missing in-platform counterpart
* transfer replay / duplicate arrival
* full fee-less continuity preservation
* restated transfer with externally supplied basis

### 16.2 Failure cases

The engine must explicitly define behavior for:

* validation failure
* referential integrity failure
* continuity-resolution failure
* reconciliation failure
* duplicate detection conflict
* insufficient-balance failure
* missing counterpart beyond expected SLA where mandatory
* event publish failure after local persistence
* query-read-model lag or partial propagation

### 16.3 Failure semantics requirement

For each failure class, the system must define:

* status
* reason code
* whether retriable
* whether blocking
* whether user-visible
* what operational action is required

---

## 17. TRANSFER_IN and TRANSFER_OUT Configurable Policies

All material transfer behavior must be configurable through versioned policy, not code forks.

### 17.1 Mandatory configurable dimensions

The following must be configurable:

* continuity mode
* lot transfer mode
* cost-basis restatement rules
* precision rules
* FX precision
* reconciliation tolerance
* cash-entry / linked-ledger mode
* position timing
* cash timing
* performance timing
* linkage enforcement
* duplicate/replay handling
* insufficient-balance handling
* strictness of counterpart pairing validation

### 17.2 Policy traceability

Every processed transfer must preserve:

* `calculation_policy_id`
* `calculation_policy_version`

### 17.3 Policy conflict rule

If two policies or policy fragments conflict in a way that changes a material outcome, the engine must not silently choose one. It must fail or park according to policy-resolution rules.

---

## 18. TRANSFER_IN and TRANSFER_OUT Gap Assessment Checklist

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

### 18.1 Characterization rule

If the current implementation already matches a requirement in this RFC, that behavior must be locked with characterization tests before refactoring or enhancement.

### 18.2 Completion rule

`TRANSFER_IN` and `TRANSFER_OUT` are complete only when:

* the full input contract is implemented
* all mandatory validations are enforced
* all mandatory calculations are implemented
* continuity behavior is implemented
* lot transfer behavior is implemented
* timing behavior is implemented
* all required metadata is preserved
* all required query outputs are available
* invariants are enforced
* the required test matrix is complete
* all remaining gaps are explicitly documented and approved

---

## 19. Appendices

### Appendix A: Error and Reason Codes

The platform must maintain a supporting catalog for:

* validation errors
* reconciliation mismatches
* policy-resolution failures
* continuity failures
* linkage failures
* duplicate/replay conflicts
* insufficient-balance failures
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

Subsequent transaction RFCs must follow the same structural pattern as this transfer RFC to ensure consistency across:

* engineering implementation
* AI-assisted coding
* QA and regression
* BA analysis
* support and ops runbooks
* audit and reconciliation

---

## 20. Final Authoritative Statement

This RFC is the canonical specification for `TRANSFER_IN` and `TRANSFER_OUT`.

If an implementation, test, support workflow, or downstream consumer behavior conflicts with this document, this document is the source of truth unless an approved exception or superseding RFC version explicitly states otherwise.
