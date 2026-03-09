# RFC-AMORTIZATION-01 Canonical Fixed Income Amortization & Accretion Specification (Premium / Discount / OID)

## 1. Document Metadata

* **Document ID:** RFC-AMORTIZATION-01
* **Title:** Canonical Fixed Income Amortization & Accretion Specification (Premium / Discount / OID)
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
| 1.0.0   | *TBD* | *TBD*  | Initial canonical amortization/accretion specification |

---

## 2. Purpose

This RFC defines the canonical, target-state specification for supporting **amortized cost** accounting for fixed income instruments in lotus-core, covering:

* **Premium amortization** (purchase price > redemption value)
* **Discount accretion** (purchase price < redemption value)
* **OID accretion** (original issue discount; economically similar to discount accretion)
* schedule-driven variants (step-up/step-down coupons, irregular schedules)
* partial redemption compatibility (amortizing/factor notes)

This RFC ensures lotus-core can produce deterministic, auditable outputs required by private banks for:

* book value / amortized cost time series
* effective yield / amortization income recognition surfaces
* correct realized capital vs FX P&L at sale/redemption
* clean vs dirty price handling and accrued interest separation
* consistent linkage across BUY/SELL/INTEREST/REDEMPTION events

> Note: Entitlement and market valuation (MTM) are not defined here. This RFC defines the **accounting cost evolution** required for correctness.

---

## 3. Scope

This RFC applies to fixed income positions including:

* plain-vanilla bonds
* callable bonds (amortization continues until call/termination event)
* amortizing/factor notes (requires principal schedule or factor path from upstream)
* structured notes where amortized cost is required by the client (bank policy)

### 3.1 Out of scope

This RFC does not define:

* curve building / discounting curve sources (analytics layer)
* full pricing/valuation (clean/dirty market price, MTM)
* tax law determination
* hedge accounting
* cancel/correct/rebook mechanics (handled by shared reversal model)

---

## 4. Referenced Standards

This RFC must be read with:

* `shared/06-common-calculation-conventions.md`
* `shared/07-accounting-cash-and-linkage.md`
* `shared/08-timing-semantics.md`
* `shared/09-idempotency-replay-and-reprocessing.md`
* `shared/10-query-audit-and-observability.md`
* `shared/11-test-strategy-and-gap-assessment.md`
* `RFC-BUY-01` (clean/dirty handling, accrued interest paid, initial cost basis)
* `RFC-INTEREST-01` (coupon payments; income vs accrual)
* `RFC-SELL-01` (sale realized capital vs FX split)
* `RFC-REDEMPTION-01` (maturity/call/partial redemption)

---

## 5. Definitions

### 5.1 Key values

* **Par / Face / Redemption value** (`redemption_value`): amount repaid at maturity per unit (often 100, sometimes factor-adjusted)
* **Clean price:** excludes accrued interest
* **Dirty price:** clean + accrued interest
* **Accrued interest:** interest earned since last coupon date but not yet paid
* **Book value / Amortized cost:** accounting cost value that evolves over time via amortization/accretion

### 5.2 Premium vs discount

At acquisition:

* `initial_clean_cost` = clean purchase price × quantity (plus fees in basis per policy)

* `initial_redemption_value` = redemption_value × quantity

* Premium if `initial_clean_cost > initial_redemption_value`

* Discount/OID if `initial_clean_cost < initial_redemption_value`

Accrued interest paid on buy is **not** part of premium/discount; it is tracked separately for net income correctness.

### 5.3 Effective interest method (EIR)

Preferred canonical method:

* amortization/accretion determined using **effective yield** over remaining cashflow schedule

Alternate methods (allowed by policy):

* straight-line amortization
* rule-of-thumb approximations (discouraged, but needed for some migrations)

---

## 6. Canonical Transaction Types

Amortization can be represented in lotus-core in either of two ways (policy-driven):

### 6.1 Mode A (recommended): Derived time series + optional journal transactions

* Amortization is computed as **derived state/time series** for each position/lot and period.
* Optional “journal-like” transactions can be emitted for audit trails.

### 6.2 Mode B: Explicit `AMORTIZATION` transactions

If the client requires explicit postings:

* `AMORTIZATION` (periodic)
* `ACCRETION` (periodic)
  (or unify as `AMORTIZATION` with direction)

This RFC standardizes both approaches. The key is consistent outputs and deterministic reproducibility.

---

## 7. Core Invariants

After implementation:

* every eligible fixed income lot has a reproducible **amortized cost schedule**
* amortized cost evolves deterministically between trade and maturity/redemption/sale
* amortization/accretion impacts:

  * book value (cost basis for realized P&L)
  * income recognition (interest income vs amortization component)
* amortization never changes **quantity**
* amortization is not a cash event (no cash leg)
* at SELL/REDEMPTION, realized capital P&L must use **current amortized cost basis**, not original cost (unless policy says otherwise)

---

## 8. Eligibility and Policy Controls

### 8.1 Eligibility

An instrument/lot is eligible for amortization if:

* `instrument_type` is fixed income (bond/note)
* `amortization_method` is enabled by policy
* required schedule inputs exist (see Section 9)

### 8.2 Mandatory configurable policies

* `amortization_enabled: bool`
* `amortization_method = EFFECTIVE_YIELD | STRAIGHT_LINE`
* `amortization_frequency = DAILY | COUPON_PERIOD | MONTHLY`
* `day_count_convention` (ACT/360, ACT/365, 30/360, etc.)
* `include_fees_in_amortized_cost: bool`
* `basis_currency_mode = LOCAL | BASE | BOTH` (default BOTH)
* `amortization_rounding_policy`
* `unrealized_mtm_separation` (ensures amortized cost is not confused with MTM)

---

## 9. Required Inputs

### 9.1 From instrument master/reference (required)

* `coupon_rate` (may be 0 for zero-coupon)
* `coupon_frequency`
* `day_count_convention`
* `issue_date` (if available)
* `maturity_date`
* `redemption_value_per_unit` (e.g., 100)
* `coupon_schedule` (dates + expected cashflows) OR sufficient data to derive schedule
* optional:

  * call schedule (call dates/prices) if instrument is callable (upstream may provide call event when exercised)

### 9.2 From acquisition transaction (BUY) / lot state (required)

Per lot:

* `acquisition_date`
* `quantity`
* `initial_clean_cost_local`
* `initial_accrued_interest_paid_local` (tracked separately)
* `initial_fees_in_basis_local` (if policy includes)
* `initial_amortized_cost_local` (derived: usually equals clean cost + fees-in-basis)
* `initial_redemption_value_local`

### 9.3 Effective yield input

The system must support:

* `effective_yield` provided by upstream (preferred), OR
* derivation from schedule + price (allowed if schedule and clean price are available)

Policy:

* `effective_yield_source = UPSTREAM | DERIVE | REQUIRE_UPSTREAM`

Recommended default: `REQUIRE_UPSTREAM` for correctness, but allow `DERIVE` for migrations.

---

## 10. Data Model (Logical)

### 10.1 Top-level: `AmortizationProfile`

Per lot (or per position if average-cost FI lots are used):

* `portfolio_id`
* `instrument_id`
* `lot_id`
* `amortization_method`
* `effective_yield`
* `day_count_convention`
* `amortization_frequency`
* `schedule_version_id` (for audit)
* `profile_status = ACTIVE | TERMINATED`
* linkage:

  * `originating_buy_transaction_id`

### 10.2 Derived schedule row: `AmortizationPeriodRow`

* `period_start_date`
* `period_end_date`
* `begin_amortized_cost_local`
* `interest_income_local` (EIR interest)
* `cash_coupon_local` (from INTEREST schedule; informational if coupon posted separately)
* `amortization_amount_local` (positive means accretion, negative means amortization; or use direction field)
* `end_amortized_cost_local`
* base equivalents
* `rounding_adjustment_local` (if required)

---

## 11. Calculation Rules

### 11.1 Clean vs dirty split rule (mandatory)

Amortization applies to **clean cost** only:

* accrued interest paid/received is handled via INTEREST/income logic and must not be amortized.

### 11.2 Initial amortized cost (default)

`initial_amortized_cost_local = initial_clean_cost_local + (fees_in_basis_local if policy includes)`

### 11.3 Effective yield method (EIR) — canonical

For each period:

1. Compute effective interest on beginning amortized cost:

`eir_interest_local = begin_amortized_cost_local × effective_yield × year_fraction(period)`

2. Cash coupon expected for the period:

`cash_coupon_local = coupon_cashflow_for_period`
(if coupon posted separately, this is still needed for schedule reconciliation)

3. Amortization amount:

`amortization_amount_local = eir_interest_local - cash_coupon_local`

* If positive: **accretion** (discount/OID)
* If negative: **amortization** (premium)

4. End amortized cost:

`end_amortized_cost_local = begin_amortized_cost_local + amortization_amount_local`

At maturity, amortized cost must reconcile to redemption value (within tolerance after rounding).

### 11.4 Straight-line method (allowed)

If policy selects straight-line:

`amortization_amount_local = (initial_amortized_cost_local - redemption_value_local) / number_of_periods_remaining`

Direction handled by sign.

### 11.5 Rounding and reconciliation (mandatory)

* Apply rounding only at defined boundaries (per period)
* Track rounding adjustments explicitly
* Enforce reconciliation at termination:

`final_amortized_cost_local ≈ redemption_value_local` within `amortization_reconciliation_tolerance`

---

## 12. Interaction with INTEREST (Coupons)

Two supported modes (policy-driven):

### 12.1 Mode 1: Coupon posted as transactions (`INTEREST`)

* INTEREST transactions represent **cash coupon** and its cash leg (if any)
* amortization schedule still computes `cash_coupon_local` for reconciliation, but it references the coupon schedule and/or observed transactions.

Income reporting must be able to split:

* coupon cash income
* amortization accretion (income-like) or premium amortization (expense-like)

### 12.2 Mode 2: Coupon implicit in schedule (no INTEREST transactions)

* amortization schedule still computes both:

  * cash coupon expected (for amortization)
  * EIR interest
* cash impacts are then out of scope for lotus-core unless upstream posts cash. (Preferred is Mode 1.)

Recommended default: Mode 1 (explicit INTEREST transactions).

---

## 13. Interaction with SELL and REDEMPTION

### 13.1 Cost basis used for realized capital P&L

At SELL/REDEMPTION effective date, the cost basis for the sold/redeemed quantity must be:

* **current amortized cost basis** for that lot/portion, not original cost (unless policy disables amortization)

For partial sells/redemptions:

* amortized cost must be allocated proportionally to the quantity disposed (and/or via lot consumption rules).

### 13.2 Realized P&L split (mandatory)

* `realized_capital_pnl = proceeds_principal - amortized_cost_basis_disposed`
* `realized_fx_pnl` computed separately per FX policy
* total = capital + fx

### 13.3 Termination of profile

When a lot is fully disposed (SELL) or fully redeemed (REDEMPTION):

* mark `AmortizationProfile.status = TERMINATED`
* store `termination_date` and reference to terminating transaction

---

## 14. Partial Redemptions and Factor Notes

If instrument redeems partially (amortizing/factor reduction):

* amortization schedule must be recalculated after each principal reduction event using:

  * new outstanding principal / factor
  * remaining cashflow schedule as provided/derived

Policy:

* `amortization_recalc_on_principal_change = REQUIRED | OPTIONAL`

Recommended: REQUIRED.

The schedule version must increment (`schedule_version_id`) with full audit trail.

---

## 15. Event Ordering and Dependency Rules

### 15.1 Required ordering guarantees

Amortization computations for a date `D` must be based on all events effective on or before `D` that impact:

* quantity outstanding (SELL/REDEMPTION)
* schedule changes (factor updates)
* yield changes (rare; typically fixed at acquisition unless reset notes; extension later)

### 15.2 Non-blocking design

lotus-core must not “lock” processing. Instead:

* compute amortization deterministically given the best-known schedule state
* if required inputs are missing, park the amortization profile and expose a reason code

---

## 16. Output / Query Contract

The platform must expose:

* amortization profile per lot (method, yield, conventions, status)
* amortization schedule rows (daily/periodic)
* current amortized cost per lot and per position
* reconciliation summary (start, end, tolerance, rounding)
* audit metadata:

  * schedule version
  * yield source
  * policy version

---

## 17. Worked Examples

### 17.1 Premium bond amortization (simplified)

* Par: 100
* Bought at clean 105
* Coupon: 5% annual, paid annually
* Effective yield: 3.8%
* Maturity: 2 years
* Quantity: 100 units

Initial amortized cost = 10,500
Redemption value = 10,000
Premium = 500 to amortize over schedule.

Each year:

* EIR interest = begin AC × 3.8%
* Cash coupon = par × 5%
* amortization = EIR interest - coupon (negative)
* end AC decreases toward 10,000.

### 17.2 Discount/OID accretion (zero coupon)

* Par: 100
* Bought at 92
* Coupon: 0
* Effective yield: derived/provided
* Maturity: 3 years

EIR interest > 0, cash coupon = 0
amortization_amount positive → AC accretes to par.

---

## 18. Test Matrix (Minimum)

### 18.1 Eligibility and input tests

* non-FI instruments are not amortized
* missing schedule/yield handled per policy (park vs reject)
* accrued interest excluded from amortized cost

### 18.2 EIR method tests

* premium bond: amortized cost declines to redemption value
* discount bond: amortized cost accretes to redemption value
* zero coupon: accretion works with no coupon transactions
* rounding reconciliation within tolerance

### 18.3 Interaction tests

* SELL uses current amortized cost basis for capital pnl
* REDEMPTION uses current amortized cost basis for capital pnl
* partial redemption triggers schedule recalculation and new schedule_version_id

### 18.4 Replay/idempotency tests

* rerun amortization generation produces identical outputs
* schedule versioning consistent after principal change events

---

## 19. Configurable Policies

Must be configurable and versioned:

* `amortization_enabled`
* `amortization_method`
* `amortization_frequency`
* `day_count_convention`
* `effective_yield_source`
* `include_fees_in_amortized_cost`
* `amortization_rounding_policy`
* `amortization_reconciliation_tolerance`
* `amortization_recalc_on_principal_change`
* whether coupons must be explicit INTEREST transactions

All outputs must preserve:

* `calculation_policy_id`
* `calculation_policy_version`

---

## 20. Final Authoritative Statement

This RFC defines the canonical specification for fixed income **Amortization/Accretion** in lotus-core, including premium amortization, discount/OID accretion, and schedule-driven variants.

It standardizes:

* amortized cost (book value) time series per lot
* effective yield and schedule inputs with auditability
* clean/dirty and accrued-interest separation
* deterministic interaction with BUY/INTEREST/SELL/REDEMPTION
* realized P&L correctness via amortized cost basis
* replay-safe, reproducible derived outputs

If any implementation, test, or downstream behavior conflicts with this RFC, this RFC is the source of truth unless an approved exception is documented.
