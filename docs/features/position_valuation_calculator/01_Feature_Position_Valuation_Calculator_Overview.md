# Feature Documentation: Position Valuation Calculator

## 1. Summary

The **`position-valuation-calculator`** is a critical backend service responsible for calculating the daily market value of every position held in every portfolio. It produces the `daily_position_snapshots` table, which is the foundational dataset used by nearly all read-APIs, including Portfolio Summary, Risk Analytics, and Concentration.

Valuation is split across two deployments. **This service is the compute worker only.**
Scheduling and reprocessing orchestration belong to `valuation_orchestrator_service`.

| Component | Owned by | Responsibility |
| --- | --- | --- |
| `ValuationConsumer` | **this service** | Consumes `valuation.job.requested` and calculates market value and unrealized P&L for one position on one day. |
| `ValuationLogic` | **this service** | Stateless valuation formulas, including dual-currency handling. |
| `ValuationRepository` | **this service** | Database access for valuation inputs and snapshot writes. |
| `ValuationScheduler` | `valuation_orchestrator_service` | Detects gaps, creates backfill jobs, and initiates reprocessing for back-dated prices. |
| `PriceEventConsumer` | `valuation_orchestrator_service` | Consumes `market_prices.persisted` and detects back-dated prices. |
| `ReprocessingWorker` | `valuation_orchestrator_service` | Drains durable reset-watermark jobs, rate-limiting the fan-out. |
| `InstrumentReprocessingStateRepository` | `valuation_orchestrator_service` | Owns `instrument_reprocessing_state`. |

Work reaches this service only as `valuation.job.requested`. To change scheduling, backfill
detection, or back-dated price handling, change `valuation_orchestrator_service`, not this one.

## 2. Key Features

* **Daily Valuation:** Calculates the mark-to-market value and unrealized P&L for every position.
* **Full Dual-Currency Support:** Correctly handles valuation for securities denominated in a different currency than the portfolio's base currency, fetching and applying the appropriate FX rates.
* **Stateful Scheduling:** `ValuationScheduler`, in `valuation_orchestrator_service`, is the sole authority for creating valuation jobs, preventing duplicate or unnecessary work.
* **Automatic Backfilling:** That same scheduler detects gaps in the `daily_position_snapshots` history and creates the jobs needed to fill them.
* **Scalable Price Reprocessing:** `valuation_orchestrator_service` detects back-dated market prices and orchestrates a durable, rate-limited reprocessing flow via a dedicated job queue and worker, ensuring stability even for widely-held securities. This service performs the resulting valuations.
* **Resilient Job Handling:** Includes logic to reset stale jobs that may have been stuck due to a worker crash, ensuring the pipeline is self-healing.