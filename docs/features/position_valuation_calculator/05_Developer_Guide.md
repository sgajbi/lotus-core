# Developer's Guide: Position Valuation Calculator

This guide provides developers with instructions for understanding, extending, and testing the `position-valuation-calculator` service.

## 1. Core Components

The service is composed of several key classes, each with a distinct responsibility:

* **`ValuationConsumer`:** The primary worker. It consumes `valuation.job.requested` jobs from Kafka and orchestrates the process of fetching data, calling the valuation logic, and saving the result.
* **`PriceEventConsumer`:** A specialized consumer that listens for `market_prices.persisted` events to detect back-dated prices and create reprocessing triggers.
* **`ValuationScheduler`:** A powerful background task that acts as the system's "brain" for data integrity. It finds gaps in position histories, creates valuation jobs, and manages the state of the reprocessing engine.
* **`ValuationLogic`:** A stateless, pure-Python class containing the core financial formulas for calculating market value and unrealized P&L, including all dual-currency logic.
* **Repositories (`ValuationRepository`, `InstrumentReprocessingStateRepository`):** These classes encapsulate all database interactions, abstracting the SQL queries away from the business logic.

## 2. Data Flow

The primary data flow for a standard valuation job is as follows:

1.  The **`ValuationScheduler`** identifies a gap in a position's history (e.g., `watermark_date` < `latest_business_date`).
2.  It creates a `PortfolioValuationJob` record in the database with `status='PENDING'`.
3.  On a subsequent cycle, the scheduler claims the `PENDING` job, updates its status to `PROCESSING`, and publishes a `PortfolioValuationRequiredEvent` to the `valuation.job.requested` Kafka topic.
4.  The **`ValuationConsumer`** consumes this event.
5.  It calls the `ValuationRepository` to fetch all necessary data (position history, price, FX rates, etc.) for the correct epoch.
6.  It executes `ValuationLogic.calculate_valuation`.
7.  It saves the result by upserting a record into the `daily_position_snapshots` table.
8.  It writes a `DailyPositionSnapshotPersistedEvent` to the `outbox_events` table within the same database transaction.
9.  The external **`OutboxDispatcher`** process publishes this final event to the `valuation.snapshot.persisted` Kafka topic for downstream consumers (like the `timeseries-generator-service`).

## 3. Extending the Logic

To add a new calculated field to the `daily_position_snapshot` table (e.g., `accrued_interest_mv`):

1.  **DB Migration:** Create an Alembic migration to add the new `accrued_interest_mv` column to the `daily_position_snapshots` table.
2.  **Update `ValuationLogic`:** Add the new calculation to the `calculate_valuation` method. This may require fetching additional data (e.g., instrument details) in the consumer.
3.  **Update `ValuationConsumer`:**
    * Fetch any new data required by the logic (e.g., call a new `InstrumentRepository` method).
    * Pass the new data to the `ValuationLogic` method.
    * Set the new field on the `DailyPositionSnapshot` object before it's saved.
4.  **Update `ValuationRepository`:** Modify the `upsert_daily_snapshot` method to include the new field in both the `INSERT` and `UPDATE` parts of the upsert statement.
5.  **Add Tests:** Add unit tests to `test_valuation_logic.py` to verify the new calculation and update integration tests as needed.