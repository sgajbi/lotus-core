# Feature Documentation: Position Valuation Calculator

## 1. Summary

The **`position-valuation-calculator`** is a critical backend service responsible for calculating the daily market value of every position held in every portfolio. It produces the `daily_position_snapshots` table, which is the foundational dataset used by nearly all read-APIs, including Portfolio Summary, Risk Analytics, and Concentration.

The service is composed of three distinct components, each with a critical responsibility for data integrity and scalability:

1.  **`ValuationConsumer`**: The primary worker that consumes `valuation.job.requested` jobs to calculate market value and unrealized P&L for a single position on a single day.
2.  **`ValuationScheduler`**: A powerful, built-in background scheduler that acts as the "brain" of the system's data integrity. It detects data gaps, creates backfill jobs, and initiates the reprocessing flow for back-dated price events by creating durable jobs.
3.  **`ReprocessingWorker`**: A dedicated background worker that consumes the durable "Reset Watermark" jobs created by the scheduler. It performs the high-volume fan-out work in a controlled, scalable manner, protecting the system from "thundering herd" scenarios.

By separating these responsibilities, this service ensures that all portfolio data is consistently valued and automatically corrected when historical data changes, without compromising system stability.

## 2. Key Features

* **Daily Valuation:** Calculates the mark-to-market value and unrealized P&L for every position.
* **Full Dual-Currency Support:** Correctly handles valuation for securities denominated in a different currency than the portfolio's base currency, fetching and applying the appropriate FX rates.
* **Stateful Scheduling:** The `ValuationScheduler` is the sole authority for creating valuation jobs, preventing duplicate or unnecessary work.
* **Automatic Backfilling:** The scheduler detects gaps in the `daily_position_snapshots` history and automatically creates the jobs needed to fill them.
* **Scalable Price Reprocessing:** Detects back-dated market prices and orchestrates a durable, rate-limited reprocessing flow via a dedicated job queue and worker, ensuring system stability even with widely-held securities.
* **Resilient Job Handling:** Includes logic to reset stale jobs that may have been stuck due to a worker crash, ensuring the pipeline is self-healing.