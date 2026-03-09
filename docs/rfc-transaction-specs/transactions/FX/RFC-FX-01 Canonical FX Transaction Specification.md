# RFC-FX-01 Canonical FX Transaction Specification (FX Spot, FX Forward, FX Swap) — Cash Settlement + Contract Exposure Model

## 1. Document Metadata

* **Document ID:** RFC-FX-01
* **Title:** Canonical FX Transaction Specification (FX Spot, FX Forward, FX Swap) — Cash Settlement + Contract Exposure Model
* **Version:** 1.1.0
* **Status:** Draft
* **Owner:** *TBD*
* **Reviewers:** *TBD*
* **Approvers:** *TBD*
* **Last Updated:** *TBD*
* **Effective Date:** *TBD*

### 1.1 Change Log

| Version | Date  | Author | Summary                                                                                 |
| ------- | ----- | ------ | --------------------------------------------------------------------------------------- |
| 1.0.0   | *TBD* | *TBD*  | Initial FX spec (cash-leg focus)                                                        |
| 1.1.0   | *TBD* | *TBD*  | Added FX contract exposure model to support trade→settlement/maturity P&L and positions |

---

## 2. Purpose

This RFC defines the canonical, target-state specification for processing **FX transactions** in lotus-core, including:

* **FX Spot**
* **FX Forward**
* **FX Swap** (near leg + far leg)

The design is **sellable-to-private-banks** and supports:

* multi-currency cash balances
* trade-date vs settlement-date views
* deterministic linkage across legs and lifecycle
* **positions** for FX exposures (forwards/swaps; optionally spot)
* P&L model readiness:

  * **realized P&L split** into `realized_capital_pnl` and `realized_fx_pnl`
  * support for **unrealized P&L time series** via contract valuation (analytics layer)
* auditability, reconciliation, idempotency, replay safety

---

## 3. Scope

This RFC applies to:

* FX spot conversions
* FX forwards from trade date to maturity settlement
* FX swaps as two linked legs (near + far)
* fees/taxes related to FX (embedded or separate postings)

### 3.1 Out of scope

This RFC does not define:

* pricing/curve building (discounting, forward curves)
* daily MTM engine implementation (analytics layer responsibility)
* NDF mechanics and fixings (can be added later)
* FX options/exotics
* collateral/margin lifecycle

However, this RFC defines the **data/position model** required so that MTM/unrealized P&L can be computed externally and stored/served consistently.

---

## 4. Referenced Standards

This RFC must be read with:

* `shared/02-glossary.md`
* `shared/06-common-calculation-conventions.md`
* `shared/07-accounting-cash-and-linkage.md`
* `shared/08-timing-semantics.md`
* `shared/09-idempotency-replay-and-reprocessing.md`
* `shared/10-query-audit-and-observability.md`
* `shared/11-test-strategy-and-gap-assessment.md`
* `shared/12-canonical-modeling-guidelines.md`
* `RFC-CHARGE-01` (if FX fees/taxes are posted separately as charge transactions)

---

## 5. Key Concepts

FX must be modeled with **two layers**:

1. **Cash Settlement Layer (Ledger Reality)**

   * actual cash debits/credits on settlement/value date

2. **Contract Exposure Layer (Economic Position)**

   * an FX contract position exists from **trade date → maturity**
   * required for **forwards and swaps** (and optionally spot)
   * enables **unrealized P&L** between trade and settlement/maturity

Both layers must be linked and auditable.

---

## 6. Definitions

### 6.1 Currency pair

Represent as:

* `pair_base_currency` / `pair_quote_currency`

Example:

* `EUR/USD` means 1 EUR priced in USD (quote).

### 6.2 Deal currencies and amounts

Let:

* `ccy_buy` = currency received at settlement
* `ccy_sell` = currency paid at settlement
* `amt_buy` = amount received (positive magnitude)
* `amt_sell` = amount paid (positive magnitude)

### 6.3 FX rate quote convention

`FxRateQuoteConvention` (required):

* `QUOTE_PER_BASE` (e.g., USD per 1 EUR for EUR/USD)
* `BASE_PER_QUOTE` (e.g., EUR per 1 USD for EUR/USD)

The engine must store the quote convention explicitly to avoid ambiguity.

### 6.4 FX contract

A contract with:

* trade date
* maturity/settlement date
* contractual exchange rate
* buy/sell currencies and notionals

---

## 7. Canonical Transaction Types

### 7.1 Business transaction types (top-level labels)

* `FX_SPOT`
* `FX_FORWARD`
* `FX_SWAP`

These represent the **economic deal type**.

### 7.2 Canonical processing components (required)

The engine must represent each FX deal as a linked set of components:

#### A) Contract exposure components (required for forward/swap; optional for spot)

* `FX_CONTRACT_OPEN`
* `FX_CONTRACT_CLOSE`
* optional lifecycle:

  * `FX_CONTRACT_RESET` (roll/novation/terms change; policy-driven extension)

#### B) Cash settlement components (required)

* `FX_CASH_SETTLEMENT_BUY`
* `FX_CASH_SETTLEMENT_SELL`

> Note: These settlement components are **not** `ADJUSTMENT` because FX itself is a two-cash-leg exchange and must remain classified as FX in reporting.

#### C) Optional related components

* `FEE` / `TAX` (separate postings, linked to the FX deal)

---

## 8. Instruments and Positions

### 8.1 Cash instruments (mandatory)

Cash legs are always booked against cash instruments per currency and cash account.

### 8.2 FX contract instrument (mandatory for forwards/swaps)

Introduce `InstrumentType = FX_CONTRACT`.

An FX contract instrument must include (at minimum):

* `fx_contract_id` (stable)
* `ccy_buy`, `ccy_sell`
* `pair_base_currency`, `pair_quote_currency`
* `contract_rate`
* `trade_date`
* `maturity_date`
* `settlement_convention` (optional)
* `portfolio_id`

### 8.3 FX contract position lifecycle

* `FX_CONTRACT_OPEN` creates an open position in the FX contract instrument
* `FX_CONTRACT_CLOSE` closes it (typically at maturity)
* between open and close, the contract is eligible for MTM/unrealized P&L calculation

---

## 9. Required Identifiers and Linkage

### 9.1 Required identifiers (all FX deals)

* `transaction_id`
* `transaction_type` (`FX_SPOT` / `FX_FORWARD` / `FX_SWAP`)
* `portfolio_id`
* `economic_event_id` (shared across all components)
* `linked_transaction_group_id` (shared across all components)
* `source_system`
* `external_reference` (recommended)
* `deal_id` / `trade_ticket_id` (recommended)

### 9.2 Component linkage (mandatory)

Each component must include:

* `component_type` (one of Section 7.2)
* `component_id` (unique within group)
* `linked_component_ids` (references within group)

### 9.3 Cash settlement linkage (mandatory)

The two cash settlement legs must be linked with:

* same `economic_event_id`
* same `linked_transaction_group_id`
* `fx_cash_leg_role = BUY | SELL`
* `linked_fx_cash_leg_id` pointing to the opposite leg

### 9.4 Contract linkage (mandatory for forward/swap)

* `fx_contract_id`
* `fx_contract_open_transaction_id`
* `fx_contract_close_transaction_id` (when available)
* settlement legs must reference the contract:

  * `settlement_of_fx_contract_id`

### 9.5 Swap linkage (mandatory for FX_SWAP)

An FX swap must include:

* `swap_event_id` (recommended)
* two leg groups:

  * `near_leg_group_id`
  * `far_leg_group_id`
* both leg groups must reference the same `swap_event_id`

---

## 10. Timing Semantics

### 10.1 Dates (required)

* `trade_date`
* `settlement_date` (value date / maturity for forward)
* optional:

  * `booking_date`
  * `value_date` (if distinct per source system)

### 10.2 Cash effective timing (policy-driven)

`fx_cash_effective_timing`:

* `SETTLEMENT_DATE` (recommended default)
* `TRADE_DATE` (rare; for certain internal booking views)

### 10.3 Contract effective timing (fixed)

* contract opens on `trade_date`
* contract closes on `settlement_date` (or on explicit close date if early termination)

### 10.4 Exposure and P&L between trade and settlement/maturity

* For forwards and swap far legs: exposure exists between trade_date and settlement_date.
* Unrealized P&L must be produced by the analytics layer via MTM valuation of `FX_CONTRACT`.

Lotus-core must store enough fields to enable that.

---

## 11. Input Contract (Normalized Fields)

### 11.1 Required inputs (all FX deals)

* `portfolio_id`
* `transaction_type` (`FX_SPOT` / `FX_FORWARD` / `FX_SWAP`)
* `trade_date`
* `settlement_date`
* `ccy_buy`, `ccy_sell`
* `amt_buy`, `amt_sell`
* `fx_rate`
* `fx_rate_quote_convention`
* `pair_base_currency`, `pair_quote_currency`
* `source_system`
* `economic_event_id` (if not provided, must be generated deterministically)
* `linked_transaction_group_id` (if not provided, must be generated deterministically)

### 11.2 Additional required inputs for forwards/swaps (contract)

* `fx_contract_id` (or deterministically generated from deal identifiers)
* `contract_rate` (may be same as fx_rate for the forward leg)
* `maturity_date` (alias of settlement_date for forward)

### 11.3 Optional inputs

* `cash_account_id_buy`, `cash_account_id_sell`
* `counterparty_id`
* `fx_rate_source`
* `spot_rate_at_trade` (for decomposition/reporting)
* `forward_points` (if available)
* fee/tax fields (embedded or separate)

---

## 12. Validation Rules

The engine must validate:

* `amt_buy >= 0`, `amt_sell >= 0`
* `fx_rate > 0`
* valid currency codes
* `ccy_buy != ccy_sell`
* `trade_date <= settlement_date` (unless policy allows back value dating)
* for forward/swap:

  * `fx_contract_id` present (or derivable)
  * `contract_rate` present
* completeness:

  * two cash settlement legs must exist (or be derivable)
  * forward/swap must include contract open/close lifecycle (or be derivable)

### 12.1 Amount-rate consistency reconciliation

Given quote convention, validate expected amounts within tolerance.

Config:

* `fx_amount_reconciliation_tolerance`

Mismatch handling (policy-driven):

* `HARD_REJECT` or `PARK`

---

## 13. Processing Flow (Deterministic)

### 13.1 Normalize and enrich

* normalize currencies and quote conventions
* generate missing identifiers deterministically
* classify fields by source: `UPSTREAM`, `DERIVED`, `CONFIGURED`, `LINKED`, `STATEFUL`

### 13.2 Create/validate contract layer (forward/swap mandatory; spot optional)

For `FX_FORWARD` and `FX_SWAP` far leg:

1. create `FX_CONTRACT_OPEN` on trade_date
2. ensure contract position exists and is OPEN until maturity
3. prepare closure linkage to settlement legs

For `FX_SPOT`:

* policy:

  * `spot_exposure_model = NONE | FX_CONTRACT`
* default: `NONE` (but allowed to model spot as a contract with maturity=settlement_date if bank wants trade-date exposure)

### 13.3 Create/validate cash settlement layer (mandatory)

* create BUY cash settlement leg
* create SELL cash settlement leg
* ensure they are linked and scheduled for settlement per policy

### 13.4 Persist and publish

* persist contract components and cash components
* publish downstream events if applicable
* ensure idempotency

---

## 14. Cash Settlement Calculation Rules

### 14.1 Cash deltas

BUY leg:

* `cash_balance_delta_local = +amt_buy` in `ccy_buy`

SELL leg:

* `cash_balance_delta_local = -amt_sell` in `ccy_sell`

### 14.2 Cashflow classification (mandatory)

* BUY leg: `cashflow_classification = FX_BUY`
* SELL leg: `cashflow_classification = FX_SELL`

### 14.3 Settlement status

Each cash leg must track:

* `settlement_status = PENDING | SETTLED | FAILED`

---

## 15. Contract Exposure Model and P&L

### 15.1 Contract position effects

`FX_CONTRACT_OPEN` creates an exposure position with fields:

* `notional_buy = amt_buy` in `ccy_buy`
* `notional_sell = amt_sell` in `ccy_sell`
* `contract_rate`
* `trade_date`, `maturity_date`

`FX_CONTRACT_CLOSE` closes the exposure at maturity (or termination).

### 15.2 Unrealized P&L between trade and maturity

Unrealized P&L must be computed by the analytics layer using:

* contract terms
* market forward rates / curves
* chosen valuation policy and timestamps

Lotus-core must support storing:

* `valuation_snapshots` (optional extension) or a separate MTM store keyed by `fx_contract_id`.

### 15.3 Realized P&L fields (mandatory)

Regardless of whether lotus-core computes realized P&L, it must output explicit fields:

* `realized_capital_pnl_local` (must be 0 for FX)
* `realized_fx_pnl_local`
* `realized_total_pnl_local`
* and base equivalents

### 15.4 Realized P&L modes (policy-driven)

`fx_realized_pnl_mode`:

* `NONE` (default; realized handled externally)
* `UPSTREAM_PROVIDED`
* `CASH_LOT_COST_METHOD` (advanced; requires cash-lot ledger)

Rules:

* **capital pnl must be 0** for FX conversion
* FX pnl may be non-zero depending on mode and base currency measurement

---

## 16. Cash Lot Ledger for Realized FX P&L (Optional Advanced)

If `CASH_LOT_COST_METHOD` enabled:

* maintain cash lots per currency and cash account
* lots created by: deposits, FX buy legs, income receipts, refunds
* lots consumed by: withdrawals, FX sell legs, fees/taxes, payments

Lot selection policy:

* `FIFO | LIFO | AVERAGE_COST | SPECIFIC_ID`

Realized FX P&L arises from differences between:

* historical cost basis of cash sold
* value of cash sold/received measured in portfolio base currency under valuation policy

---

## 17. FX Forward Specific Requirements

* contract must exist from trade date to maturity
* cash settlement legs must occur on maturity date
* optional storage of:

  * `spot_rate_at_trade`
  * `forward_points`

---

## 18. FX Swap Specific Requirements

### 18.1 Structure

An FX swap must be represented as:

* near leg group (spot-like settlement)
* far leg group (forward-like settlement + contract exposure)

### 18.2 Processing order

* near leg contract exposure:

  * optional; often near leg settles quickly
* far leg contract exposure:

  * mandatory (exposure exists until far maturity)
* far cash settlement posted only at far maturity

---

## 19. Fees and Taxes for FX (Optional)

Fees/taxes may be:

* embedded in amounts (reducing amt_buy or increasing amt_sell), or
* posted separately as `FEE`/`TAX` transactions.

If separate:

* must share `linked_transaction_group_id` and `economic_event_id`
* must reference `deal_id` / `fx_contract_id` where applicable

---

## 20. Output / Query Contract

The platform must expose:

### 20.1 FX deal view

* deal identifiers, pair, rate, dates
* contract identifiers (if applicable)
* linkage ids

### 20.2 Contract exposure view (forwards/swaps; optional spot)

* `fx_contract_id`, notionals, currencies, trade/maturity dates
* lifecycle status: `OPEN | CLOSED`
* links to settlement legs

### 20.3 Cash settlement view

* both legs with deltas, currencies, settlement status
* trade vs settlement effective timing

### 20.4 P&L view

* explicit realized pnl split (capital=0, fx possibly non-zero)
* pointers to unrealized MTM series keyed by `fx_contract_id`

---

## 21. Worked Examples

### 21.1 FX Spot USD→SGD (cash settlement only)

* trade_date: 2026-04-01
* settlement_date: 2026-04-03
* sell USD 10,000
* buy SGD 13,450
* rate: 1.3450 SGD per USD (`QUOTE_PER_BASE` with base=USD, quote=SGD)

Cash legs on settlement date:

* SGD +13,450
* USD -10,000

Spot exposure model:

* default `NONE` (no contract position), optional `FX_CONTRACT` for trade-date exposure reporting.

### 21.2 FX Forward EUR→USD (contract + settlement)

* trade_date: 2026-04-01
* maturity_date: 2026-07-01
* sell EUR 1,000,000
* buy USD 1,095,000
* contract_rate: 1.0950 USD per EUR

On trade_date:

* `FX_CONTRACT_OPEN` creates exposure.

Between trade and maturity:

* MTM/unrealized P&L computed externally for `fx_contract_id`.

On maturity:

* cash legs:

  * EUR -1,000,000
  * USD +1,095,000
* `FX_CONTRACT_CLOSE`

### 21.3 FX Swap (near + far)

Near leg group:

* settle 2026-04-03
* USD -5,000,000
* CHF +4,550,000

Far leg group (forward exposure):

* maturity 2026-07-03
* CHF -4,560,000
* USD +5,010,000
* `FX_CONTRACT_OPEN` exists until far maturity.

---

## 22. Test Matrix (Minimum)

### 22.1 Validation tests

* reject same currency
* reject negative amounts
* reject zero/negative rate
* amount-rate reconciliation within tolerance
* forward/swap require contract fields

### 22.2 Spot tests

* two cash legs created/linked
* settlement timing applied correctly
* optional spot contract exposure enabled/disabled by policy

### 22.3 Forward tests

* contract opens on trade date and remains open
* no cash moves until maturity (default policy)
* contract closes at maturity and links to settlement legs
* idempotency prevents duplicates

### 22.4 Swap tests

* near and far groups linked under swap_event_id
* far contract exposure exists until far maturity
* far cash legs applied only at far maturity

### 22.5 P&L tests

* realized capital pnl is always 0
* realized fx pnl fields are present (0 if mode NONE)
* upstream-provided realized pnl stored correctly
* cash-lot mode produces fx pnl when enabled (separate test suite)

### 22.6 Fee/tax tests

* separate fee/tax postings link to FX group
* embedded fee handling does not double count

---

## 23. Configurable Policies

Must be configurable and versioned:

* `fx_cash_effective_timing`
* `fx_amount_reconciliation_tolerance`
* `spot_exposure_model = NONE | FX_CONTRACT`
* `fx_realized_pnl_mode = NONE | UPSTREAM_PROVIDED | CASH_LOT_COST_METHOD`
* cash-lot lot-selection policy (if enabled)
* rate convention normalization policy
* precision/rounding
* strictness for requiring explicit cash accounts
* embedded vs separate fee validation

All processed records must preserve:

* `calculation_policy_id`
* `calculation_policy_version`

---

## 24. Final Authoritative Statement

This RFC defines the canonical specification for **FX Spot**, **FX Forward**, and **FX Swap** processing in lotus-core using a two-layer model:

1. **Cash settlement layer** (two linked cash legs on settlement dates)
2. **Contract exposure layer** (FX contract positions for forwards/swaps; optional for spot)

It standardizes linkage, timing semantics, position readiness for MTM/unrealized P&L, explicit realized P&L structure (capital vs FX split), auditability, and replay safety.

If any implementation, test, or downstream behavior conflicts with this RFC, this RFC is the source of truth unless an approved exception is documented.
