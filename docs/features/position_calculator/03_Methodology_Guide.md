# Methodology Guide: Position Processing

This guide details the methodologies used by the position module inside the unified `portfolio_transaction_processing_service` runtime to build the `position_history` and to trigger reprocessing.

## 1. Position State Calculation

For each transaction, the service calculates the next position state by updating the quantity and cost basis of the previous state. The logic varies significantly by transaction type.

The following table details how each transaction type affects the running state of a position:

| Transaction Type | Quantity Calculation | Cost Basis Calculation |
| :--- | :--- | :--- |
| `BUY` | `quantity + transaction.quantity` | `cost_basis + transaction.net_cost` |
| `SELL` | `quantity - transaction.quantity` | `cost_basis + transaction.net_cost` (Note: `net_cost` is negative for a sell) |
| `TRANSFER_OUT` | `quantity - transaction.quantity` | `cost_basis + transaction.net_cost` (Note: `net_cost` is negative for a transfer out) |
| `TRANSFER_IN` | `quantity + transaction.quantity` | `cost_basis + transaction.gross_transaction_amount` |
| `DEPOSIT` | `quantity + transaction.gross_transaction_amount` | `cost_basis + transaction.gross_transaction_amount` |
| `WITHDRAWAL` | `quantity - transaction.gross_transaction_amount` | `cost_basis - transaction.gross_transaction_amount` |
| `FEE`, `TAX` | `quantity - transaction.gross_transaction_amount` | `cost_basis - transaction.gross_transaction_amount` |
| `DIVIDEND`, `INTEREST`| No change | No change |

## 2. Back-Dated Transaction Detection

The service uses a robust method to determine if an incoming transaction is back-dated, which prevents reprocessing from being missed due to data pipeline lag.

1.  **Fetch State**: For an incoming transaction, the service fetches two key dates for the `(portfolio_id, security_id)` key:
    * The `watermark_date` from the `position_state` table.
    * The date of the latest `position_history` row.
    * The date of the most recent `daily_position_snapshot` for the current epoch.
2.  **Determine Effective Date**: `plan_backdated_recalculation()` calculates the
    `effective_completed_date` as the **maximum of all three**, treating a missing history or
    snapshot date as the epoch start. Position history is easy to overlook: when it is ahead of both
    the watermark and the snapshots, the runtime still advances the epoch and rebuilds. Omitting it
    predicts no rebuild where one happens, which matters for tests as much as for operations.
3.  **Compare**: The transaction is considered back-dated if its `transaction_date` is **earlier than** the `effective_completed_date`. Transactions occurring on the same day are not considered back-dated.