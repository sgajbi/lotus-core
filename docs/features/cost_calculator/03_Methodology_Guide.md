# Methodology Guide: Cost Calculator

This guide explains the methodologies used by the `cost_calculator_service` to ensure accurate and auditable financial calculations.

## 1. Core Principle: Full History Recalculation

To guarantee correctness in the face of back-dated or corrected transactions, the service employs a **full history recalculation** strategy. For every new transaction it processes for a given security, it performs the following steps:

1.  **Fetch History**: It queries the database for **all** existing transactions for that specific `(portfolio_id, security_id)` key.
2.  **Create Timeline**: It combines the new transaction with the fetched historical ones.
3.  **Sort**: It sorts the complete list of transactions chronologically.
4.  **Recalculate**: It processes the entire sorted timeline from the very beginning, recalculating the cost basis and realized P&L for every single transaction in the sequence using the portfolio's configured cost basis method.
5.  **Persist Affected Suffix**: It updates the incoming transaction and every later transaction whose calculated cost or realized P&L can be affected, in deterministic timeline order and one database transaction.
6.  **Publish Once**: It publishes only the incoming processed transaction event. The combined position path rebuilds from the corrected canonical rows, so publishing the corrected suffix would apply later positions twice.

Any engine error in the recalculated timeline fails the operation before suffix persistence. This method, while computationally intensive, is deterministic and robust, ensuring that later canonical cost rows do not remain stale when data arrives out of order.

## 2. Cost Basis Strategy: First-In, First-Out (FIFO)

The **FIFO** accounting method is the system's default.

* **Cost Lots**: When a `BUY` transaction occurs, a "cost lot" is created and stored in memory. This lot contains the quantity purchased and the net cost per share.
* **Disposition**: When a `SELL` transaction occurs, the system consumes the oldest available cost lots first to determine the cost of goods sold (COGS) for the P&L calculation. If a sell is larger than the oldest lot, it consumes it entirely and moves to the next oldest lot until the full quantity is accounted for.

## 3. Cost Basis Strategy: Average Cost (AVCO)

The **AVCO** method calculates gains and losses based on the average cost of all shares held at the time of sale.

* **Running Average**: The system maintains a running total of the `quantity`, `total_cost_local`, and `total_cost_base` for each security.
* **On Purchase (BUY)**: When a `BUY` occurs, the transaction's quantity and net costs (both local and base) are added to the running totals.
* **On Sale (SELL)**: When a `SELL` occurs, the Cost of Goods Sold (COGS) is calculated by multiplying the quantity sold by the current average cost per share (`total_cost / total_quantity`). This calculation is performed for both the local and base currency totals.

## 4. Dual-Currency Calculations

The engine is designed to correctly handle portfolios that trade in multiple currencies. It tracks all costs and P&L in both the instrument's **local currency** and the portfolio's **base currency**.

* **On Purchase (BUY)**:
    1.  The `net_cost_local` is calculated in the instrument's currency (e.g., EUR).
    2.  The historical FX rate from the transaction date is fetched and applied to calculate the `net_cost` in the portfolio's base currency (e.g., USD).
    3.  The resulting cost lot (FIFO) or running totals (AVCO) store **both** the local and base cost.

* **On Sale (SELL)**:
    1.  **Proceeds**: The sale proceeds are calculated in both local and base currency using the FX rate on the **sale date**.
    2.  **Cost of Goods Sold (COGS)**: The cost is retrieved using the portfolio's configured method (FIFO or AVCO). The base currency COGS is already "baked in" from the original purchase date's FX rate(s).
    3.  **Realized P&L**: The P&L is calculated in both currencies: `P&L = Proceeds - COGS`. This method correctly captures the total P&L, which is a combination of the asset's price movement and the fluctuation in the FX rate between the buy and sell dates.

## 5. Handling of Specific Transaction Types

The service uses specific strategies for different transaction types to ensure they are handled correctly:

* **`TRANSFER_IN` / `DEPOSIT`**: These are treated like purchases. A `TRANSFER_IN` of a security creates a new cost lot with a cost basis equal to the market value on the date of transfer. A `DEPOSIT` of cash creates a cost lot for the cash position.
* **`TRANSFER_OUT` / `WITHDRAWAL`**: These are treated like dispositions. They consume existing cost lots (either security lots or cash lots) to correctly reduce the position's quantity and cost basis, but they generate **no realized P&L**.
* **`DIVIDEND` / `INTEREST`**: These are treated as pure income and have no impact on the cost basis of the underlying security.
