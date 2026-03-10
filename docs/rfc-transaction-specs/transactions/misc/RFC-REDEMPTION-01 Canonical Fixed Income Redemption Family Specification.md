# RFC-REDEMPTION-01 Canonical Fixed Income Redemption Family Specification (Maturity / Call / Partial Redemption)

## 1. Document Metadata

- **Document ID:** RFC-REDEMPTION-01
- **Title:** Canonical Fixed Income Redemption Family Specification (Maturity / Call / Partial Redemption)
- **Version:** 1.0.0
- **Status:** Draft
- **Owner:** _TBD_
- **Reviewers:** _TBD_
- **Approvers:** _TBD_
- **Last Updated:** _TBD_
- **Effective Date:** _TBD_

### 1.1 Change Log

| Version | Date | Author | Summary |
|---|---|---|---|
| 1.0.0 | _TBD_ | _TBD_ | Initial canonical redemption family specification |

---

## 2. Purpose

This RFC defines the canonical, target-state specification for processing **Fixed Income Redemption** events in lotus-core, including:

- **Maturity Redemption** (final principal repayment at maturity)
- **Call Redemption** (issuer call, full redemption before maturity)
- **Partial Redemption** (partial call, amortizing redemption, factor reduction)

The objective is to support production-grade private banking / wealth-tech requirements for:

- positions (quantity and lifecycle)
- cost basis allocation and reconciliation
- cash movements and dual accounting (product + cash settlement linkage)
- realized P&L split into:
  - `realized_capital_pnl`
  - `realized_fx_pnl`
  - `realized_total_pnl`
- timing semantics (effective vs value/settlement vs booking)
- auditability, replay safety, and deterministic processing order

---

## 3. Scope

This RFC applies to **principal redemption** events for:

- bonds
- structured notes with defined redemption mechanics
- certificates with redemption/factor events
- any security where upstream generates redemption transactions into lotus-core

### 3.1 Out of Scope

This RFC does not define:

- entitlement calculation logic (performed upstream)
- pricing/valuation methodology for MTM/unrealized P&L (analytics layer)
- coupon accrual engines (handled by `INTEREST` RFC and/or analytics layer)
- complex derivative payoff engines (analytics layer)
- cancel/correct/rebook mechanics (handled by `RFC-CA-REVERSAL-01` or shared reversal model if generalized)

---

## 4. Referenced Standards

This RFC must be read with:

- `shared/07-accounting-cash-and-linkage.md`
- `shared/08-timing-semantics.md`
- `shared/09-idempotency-replay-and-reprocessing.md`
- `shared/10-query-audit-and-observability.md`
- `shared/11-test-strategy-and-gap-assessment.md`
- `RFC-CHARGE-01` (if fees/taxes are posted separately)
- `RFC-INTEREST-01` (for coupon cashflows and accrued interest settlement)
- `RFC-SELL-01` semantics for realized P&L structure (capital vs FX split)

---

## 5. Definitions

### 5.1 Redemption vs Coupon

- **Redemption:** repayment of **principal** (par, factor-adjusted notional, or call-price principal component)
- **Coupon/Interest:** periodic income cashflow (handled by INTEREST), may be paid at redemption as final/early coupon

### 5.2 Redemption Amount Concepts

For a redemption event:

- `redeemed_quantity` (units redeemed; may be full or partial)
- `redemption_price` (price per unit; may be par or call price)
- `principal_proceeds_local` (principal proceeds in security currency)
- `accrued_interest_proceeds_local` (if settled together; optional)
- `total_cash_proceeds_local = principal_proceeds_local + accrued_interest_proceeds_local - embedded_fees - embedded_taxes`

### 5.3 Factor-Based Instruments

Some instruments redeem via factor changes (e.g., amortizing notes). Upstream may provide:

- `old_factor`
- `new_factor`

Lotus-core must handle either explicit `redeemed_quantity` **or** factor inputs (policy-driven), but must never infer entitlement logic beyond deterministic transformations.

---

## 6. Canonical Transaction Types

### 6.1 Product-leg redemption types

- `MATURITY_REDEMPTION`
- `CALL_REDEMPTION`
- `PARTIAL_REDEMPTION`

### 6.2 Cash-leg settlement type

- `ADJUSTMENT` (cash instrument settlement leg)

### 6.3 Optional linked overlays

- `INTEREST` (final coupon) and/or `ACCRUED_INTEREST_SETTLEMENT` (if modeled separately)
- `FEE`
- `TAX`
- `CASH_IN_LIEU` (rare for odd-lot/fractional redemption mechanics)

---

## 7. Dual-Leg Accounting Model (Mandatory)

A redemption with cash impact must have **two linked legs**:

1. **Product leg** (`*_REDEMPTION`) booked on the security instrument
2. **Cash leg** (`ADJUSTMENT`) booked on the cash instrument (cash account)

Both legs must be linked by:

- `economic_event_id`
- `linked_transaction_group_id`
- explicit cross-links (recommended):
  - product leg: `linked_cash_transaction_id`
  - cash leg: `linked_product_transaction_id`

This dual-leg model is mandatory because redemption changes both **position** and **cash**.

---

## 8. Timing Semantics

### 8.1 Dates (required)

- `effective_date` (economic event date; often call/maturity date)
- `settlement_date` (cash value date)
- optional `booking_date`

### 8.2 Timing Policy (required)

Configurable:

- `redemption_cash_effective_timing = SETTLEMENT_DATE | EFFECTIVE_DATE | BOOKING_DATE`

Recommended default: `SETTLEMENT_DATE`.

### 8.3 Recognition timing (required)

Configurable:

- `redemption_pnl_recognition_timing = EFFECTIVE_DATE | SETTLEMENT_DATE | BOOKING_DATE`

Default: `EFFECTIVE_DATE` (typical economic view) unless client requires accounting-booking view.

---

## 9. Input Contract (Normalized)

### 9.1 Required fields (product leg)

- `transaction_type` (`MATURITY_REDEMPTION` / `CALL_REDEMPTION` / `PARTIAL_REDEMPTION`)
- `portfolio_id`
- `instrument_id`
- `effective_date`
- `settlement_date`
- `redeemed_quantity` (>= 0)
- `redemption_price` (>= 0)
- `security_currency`
- `portfolio_base_currency`
- `fx_rate_to_base` (required if security_currency != base_currency)
- `economic_event_id`
- `linked_transaction_group_id`
- `source_system`
- `external_reference` (recommended)

### 9.2 Optional fields (product leg)

- `accrued_interest_proceeds_local`
- `principal_proceeds_local` (if provided explicitly; else derived)
- `redemption_price_type` (`PAR`, `CALL_PRICE`, `MARKET_PRICE`)
- `call_reason` / `call_type` (issuer call classification)
- `old_factor`, `new_factor`
- `embedded_fee_amount_local`, `embedded_tax_amount_local` (if not separate transactions)
- `valuation_price_at_effective_date` (optional; only for synthetic flows/performance)

### 9.3 Required fields (cash leg)

- `transaction_type = ADJUSTMENT`
- `cash_account_id`
- `cash_currency`
- `cash_amount_local` (signed; inflow positive, outflow negative)
- `settlement_date`
- linkage:
  - same `economic_event_id` and `linked_transaction_group_id`
  - `linked_product_transaction_id` (recommended)

---

## 10. Validation Rules

Must validate:

- `redeemed_quantity >= 0`
- `redemption_price >= 0`
- `effective_date` and `settlement_date` present
- instrument is eligible for redemption (instrument metadata)
- cash leg exists for cash-settled redemption (unless policy allows late-arriving settlement)
- proceeds reconciliation between derived vs upstream-provided fields within tolerance

Hard-fail unless policy override:

- missing cash leg where required
- negative price/quantity
- redeemed quantity exceeds available position quantity (unless explicitly configured for short/borrow semantics)
- unreconcilable cost-basis allocation mismatch beyond tolerance

Configurable tolerance:
- `redemption_reconciliation_tolerance`

---

## 11. Calculation Rules

### 11.1 Principal proceeds (local)

Default:

`principal_proceeds_local = redeemed_quantity × redemption_price`

If upstream provides `principal_proceeds_local`, lotus-core must reconcile it with the derived value within tolerance.

### 11.2 Total proceeds (local)

If accrued interest is settled together:

`total_cash_proceeds_local = principal_proceeds_local + accrued_interest_proceeds_local - embedded_fees_local - embedded_taxes_local`

If accrued interest is not provided, treat it as `0` and rely on separate `INTEREST` postings if expected.

### 11.3 Cash leg amount

If `cash_currency == security_currency`:

`cash_amount_local = +total_cash_proceeds_local`

If `cash_currency != security_currency`:

- preferred: upstream supplies the cash leg amount in cash currency
- allowed: lotus-core derives using configured FX policy and provided FX rates

### 11.4 Cost basis allocation for redeemed quantity

Lotus-core currently allocates cost basis from lots using supported policy:

- `FIFO | AVCO`

Allocated basis:

`allocated_cost_basis_local = Σ(consumed_lot_basis_local)`

### 11.5 Realized P&L (local)

Realized capital P&L must be computed on **principal only**:

`realized_capital_pnl_local = principal_proceeds_local - allocated_cost_basis_local`

Realized FX P&L is policy-driven and must be stored separately:

- `realized_fx_pnl_local` (may be `0` if mode `NONE`)

Total:

`realized_total_pnl_local = realized_capital_pnl_local + realized_fx_pnl_local`

### 11.6 Base currency conversion

Convert and store base-currency equivalents (policy-driven):

- `principal_proceeds_base`
- `allocated_cost_basis_base`
- `realized_capital_pnl_base`
- `realized_fx_pnl_base`
- `realized_total_pnl_base`

Default:

`amount_base = amount_local × fx_rate_to_base`

---

## 12. Income Treatment (Coupon / Accrued Interest)

### 12.1 Final coupon paid separately

If upstream posts a separate `INTEREST` transaction:

- process using `RFC-INTEREST-01`
- link to the redemption via `linked_transaction_group_id` (recommended)

### 12.2 Accrued interest included in redemption cash

If accrued interest is included in the same settlement:

- must be stored explicitly in `accrued_interest_proceeds_local`
- must be classified as income for reporting (e.g., `income_classification = INTEREST_INCOME`)
- must not affect `realized_capital_pnl` computation (principal-only)

### 12.3 No double counting rule

If both:
- separate interest transaction exists **and**
- accrued interest is embedded in redemption cash,

then the event must fail/park unless policy explicitly supports reconciliation and netting rules.

---

## 13. Position Effects

### 13.1 Quantity

- full redemption: position quantity becomes `0`
- partial redemption: position quantity decreases by `redeemed_quantity`

### 13.2 Lot effects

- redeemed lots are consumed/closed per lot policy
- remaining lots retain acquisition dates and held-since properties

### 13.3 Synthetic flows (optional; position-level only)

If required strictly for **position-level performance/contribution continuity** (not portfolio-level cash/performance):

- create a synthetic product-leg outflow at MVT for redeemed quantity

Config:
- `redemption_synthetic_flow_mode = NONE | MVT_PRICE_X_QTY`

Default: `NONE` (because real cash exists).

Synthetic flows must never create real cash legs.

---

## 14. Processing Order and Dependencies

Default dependency-safe order:

1. process product redemption leg:
   - validate
   - consume lots
   - compute principal proceeds and realized P&L
2. process cash `ADJUSTMENT` leg:
   - update cash balance on `redemption_cash_effective_timing`
3. process linked interest legs (if any)
4. process linked fees/taxes (if any)
5. reconcile and mark event complete

Arrival order must not be assumed.

If required dependencies are missing:
- event state becomes `PENDING_DEPENDENCIES` or `PARKED` per policy.

---

## 15. Idempotency and Replay

### 15.1 Idempotency keys (recommended)

Product leg:
- `(source_system, external_reference, portfolio_id, instrument_id, effective_date, transaction_type)`

Cash leg:
- `(source_system, external_reference, portfolio_id, cash_account_id, settlement_date, cash_amount_local)`

### 15.2 Replay rule

Replay must not duplicate:

- lot consumption
- cash posting
- realized P&L records
- interest overlays

---

## 16. Output Contract

Expose:

- enriched redemption transaction view (product leg)
- cash settlement view (cash leg)
- realized P&L breakdown:
  - capital / FX / total (local + base)
- lot consumption summary (quantities + basis allocated)
- principal vs interest decomposition
- timing fields and applied policy metadata
- audit metadata and reconciliation summary

---

## 17. Worked Examples

### 17.1 Example A: Maturity redemption at par with accrued interest in same settlement

- Holding: 100 units bond
- Cost basis: 99.00 per unit → total basis 9,900
- Redemption: 100 units at 100.00
- Accrued interest included: 50.00
- Currency/base: USD/USD

Principal proceeds: `100 × 100 = 10,000`  
Allocated basis: `9,900`  
Realized capital pnl: `100`  
Interest income: `50`  
Cash inflow: `10,050`

### 17.2 Example B: Partial call above par, interest posted separately

- Holding: 200 units, avg basis 99 → total basis 19,800
- Call: redeem 80 units at 101
- Interest: separate `INTEREST` transaction

Principal proceeds: `80 × 101 = 8,080`  
Allocated basis (FIFO example): `80 × 99 = 7,920`  
Realized capital pnl: `160`  
Remaining position: `120 units`

### 17.3 Example C: Cross-currency redemption (EUR bond, base SGD)

- Principal proceeds: 10,000 EUR
- Basis: 9,700 EUR
- FX rate to base: 1.45 SGD/EUR

Realized capital pnl local: `300 EUR`  
Realized capital pnl base: `435 SGD`  
Realized FX pnl: policy-driven (may be 0, upstream-provided, or derived via cash-lot mode)

---

## 18. Test Matrix (Minimum)

### 18.1 Validation tests

- reject negative quantity/price
- reject redeem quantity > position (unless configured)
- missing cash leg handling (park vs reject per policy)
- proceeds reconciliation tolerance checks

### 18.2 Calculation tests

- maturity redemption at par with embedded accrued interest
- call redemption above par
- partial redemption with FIFO and AVCO
- embedded vs separate fees/taxes
- cross-currency base conversion fields populated
- realized P&L fields always present and split (capital vs FX)

### 18.3 Position/lot tests

- full redemption closes position and lots
- partial redemption consumes correct lots and preserves remaining lots

### 18.4 Replay/idempotency tests

- replay does not duplicate cash or lot consumption
- event can be reversed/corrected via the global reversal model

---

## 19. Configurable Policies

Must be configurable and versioned:

- `redemption_cash_effective_timing`
- `redemption_pnl_recognition_timing`
- lot selection policy (`FIFO/AVCO`)
- basis rounding/precision rules
- proceeds reconciliation tolerance
- realized FX pnl mode (`NONE | UPSTREAM_PROVIDED | CASH_LOT_COST_METHOD`)
- redemption synthetic flow mode (`NONE | MVT_PRICE_X_QTY`)
- strictness for requiring linked interest/coupon legs
- strictness for disallowing double counting of embedded+separate interest

All records must preserve:

- `calculation_policy_id`
- `calculation_policy_version`

---

## 20. Final Authoritative Statement

This RFC defines the canonical specification for the **Fixed Income Redemption Family** in lotus-core (maturity, call, and partial redemptions), including:

- linked product + cash settlement legs
- deterministic lot/basis allocation
- explicit realized P&L split (capital vs FX) in local and base
- correct handling of accrued interest and final coupons (embedded or separate)
- timing semantics and replay safety

If any implementation, test, or downstream behavior conflicts with this RFC, this RFC is the source of truth unless an approved exception is documented.
