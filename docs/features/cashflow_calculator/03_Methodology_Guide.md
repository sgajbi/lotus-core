# Methodology Guide: Cashflow Calculator

This guide details the rule-based methodology used by the `cashflow_calculator_service` to generate cash flow records from transactions.

## 1. Rule-Based Mapping

The core of the service is a **database-driven configuration** that maps every supported `transaction_type` to a set of cash flow attributes. This ensures that the process is deterministic and consistent. The logic is stored in the `cashflow_rules` table.

The key attributes determined by the rules are:

* **Classification:** The financial purpose of the cash flow (e.g., `INVESTMENT_OUTFLOW`, `INCOME`).
* **Timing:** Whether the flow should be considered at the Beginning-of-Day (`BOD`) or End-of-Day (`EOD`) for performance calculations.
* **Flow Type:** Booleans (`is_position_flow`, `is_portfolio_flow`) that determine how the flow impacts TWR calculations.

The following table details the complete rule set as seeded in the database:

| Transaction Type | Classification | Timing | Is Position Flow? | Is Portfolio Flow? |
| :--- | :--- | :--- | :--- | :--- |
| `BUY` | `INVESTMENT_OUTFLOW` | `BOD` | Yes | No |
| `SELL` | `INVESTMENT_INFLOW` | `EOD` | Yes | No |
| `DIVIDEND` | `INCOME` | `EOD` | Yes | No |
| `INTEREST` | `INCOME` | `EOD` | Yes | No |
| `FEE` | `EXPENSE` | `EOD` | Yes | **Yes** |
| `TAX` | `EXPENSE` | `EOD` | Yes | No |
| `TRANSFER_IN` | `TRANSFER` | `BOD` | Yes | **Yes** |
| `DEPOSIT` | `CASHFLOW_IN` | `BOD` | Yes | **Yes** |
| `TRANSFER_OUT` | `TRANSFER` | `EOD` | Yes | **Yes** |
| `WITHDRAWAL` | `CASHFLOW_OUT` | `EOD` | Yes | **Yes** |

## 2. Amount Calculation & Sign Convention

The service follows a standard financial sign convention: **inflows to the portfolio are positive, and outflows are negative.**

* The `amount` is derived from the transaction's `gross_transaction_amount`.
* For transactions classified as `INVESTMENT_INFLOW`, `INCOME`, `CASHFLOW_IN`, or `TRANSFER_IN`, the resulting amount is positive.
* For all other classifications (`INVESTMENT_OUTFLOW`, `EXPENSE`, `CASHFLOW_OUT`, `TRANSFER_OUT`), the resulting amount is negative.
* The `trade_fee` from the transaction is included in the calculation. For a `BUY`, the fee increases the outflow (making it more negative). For a `SELL`, the fee decreases the inflow.

## 3. Portfolio Cashflow Projection Product

`PortfolioCashflowProjection:v1` is the query-service source-data product for daily operational
cashflow projection. Its implementation-backed methodology is maintained separately from this
calculator overview because it is a downstream read product over persisted cashflow and transaction
evidence:

- [Portfolio Cashflow Projection Methodology](../../methodologies/source-data-products/portfolio-cashflow-projection.md)
