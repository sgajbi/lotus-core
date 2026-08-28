# Feature Documentation: Cost Processing

## 1. Summary

**Cost processing** is the backend data-enrichment capability, owned by the unified `portfolio_transaction_processing_service` runtime, that calculates the **cost basis** of security purchases and the **realized profit and loss (P&L)** on sales. It consumes raw (but persisted) transaction events and produces new, enriched events with these calculated financial figures.

P&L stays accurate even for back-dated trades because cost processing runs in one of **two modes** per transaction: a checkpointed **ordered append** for eligible in-order activity, and a **full history recalculation** as the fallback. The cost-basis engine lives directly under the service package, which makes ownership and deployment boundaries explicit.

## 2. Key Features

* **Realized P&L Calculation**: Computes the realized gain or loss for every `SELL` transaction based on a configured cost basis methodology.
* **Cost Basis Tracking**: Tracks the cost basis of all open positions using a tax lot (FIFO) or average cost (AVCO) accounting system.
* **Ordered Append (normal path)**: For eligible in-order activity, `CostBasisCalculationCoordinator.calculate()` restores only the required open-lot or average-cost checkpoint state and processes the incoming transaction against it. It does **not** re-fetch the security's history, so normal-path processing is not O(history).
* **Full History Recalculation (fallback)**: For back-dated or checkpoint-ineligible transactions, the service re-fetches the complete transaction history for that security and recalculates its cost basis timeline from the beginning. It atomically persists the incoming transaction and the affected later suffix, while publishing only the incoming processed event. This prevents stale later realized P&L without duplicate downstream position application when historical data arrives out of order.

  The [methodology guide](./03_Methodology_Guide.md) states the exact conditions that select each mode. Capacity planning should treat rebuild as the exceptional path.
* **Dual-Currency Support**: Accurately calculates cost and P&L for portfolios that trade securities in currencies different from their base currency, using the appropriate historical FX rates.
* **Configurable Cost Method**: The system supports multiple cost basis methods. The method is a configurable attribute on each portfolio, allowing clients to use either **First-In, First-Out (FIFO)** or **Average Cost (AVCO)** to meet their accounting requirements.
