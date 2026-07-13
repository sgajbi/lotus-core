# Shared Requirement: Common Calculation Conventions

## Purpose

Define shared calculation rules that apply across transaction types.

## Numeric Rules

- all business-critical numeric values must use decimal-safe arithmetic
- floating-point arithmetic must not be used for financial calculations
- precision and rounding must be policy-driven and documented

## Base and Local Currency

Each transaction RFC must define:

- local amount fields
- base amount fields
- fx source
- fx precision and rounding

## Required Explicitness

If a transaction produces realized pnl, the transaction RFC must define both:

- realized capital pnl
- realized fx pnl

If a transaction does not realize pnl, the RFC must define whether those fields are explicit zero values or not applicable.

## Formula Rule

Every transaction RFC must define:

- input values
- derived values
- formula order
- default formulas
- policy-driven variants

## Settlement Cash Rule

For ordinary BUY, SELL, DIVIDEND, and INTEREST transactions, one domain policy must resolve the
transaction fee, signed settlement amount, and ledger direction. Fee components take precedence
over the aggregate `trade_fee` when any component is present.

```text
buy settlement = -(gross amount + resolved transaction fee)
sell settlement = gross proceeds - resolved transaction fee
dividend settlement = gross dividend - resolved transaction fee
interest income settlement = pre-fee net interest - resolved transaction fee
interest expense settlement = -(pre-fee net interest + resolved transaction fee)
```

SELL, DIVIDEND, and INTEREST income settlement must remain strictly positive before the inflow sign
is applied. A zero or negative result is a hard rejection; absolute-value normalization must not
turn it into an apparent inflow. Generated cash legs and persisted product cashflows must consume
the same signed settlement result.
