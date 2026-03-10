# Developer's Guide: Timeseries Generation and Portfolio Aggregation

This guide provides developers with instructions for understanding and extending the split time-series layer.

## 1. Architecture Overview

The platform is designed as a two-stage pipeline to transform daily snapshots into the final, aggregated time-series data used for analytics.

1.  **Stage 1: Position Time-Series Generation**
    * The **`PositionTimeseriesConsumer`** in `timeseries_generator_service` listens for `daily_position_snapshot_persisted` events.
    * For each event, it fetches the snapshot, the previous day's snapshot, and all of the day's cash flows for that specific security.
    * It then calls **`PositionTimeseriesLogic`** to calculate and create a single `position_timeseries` record.
    * Finally, it idempotently creates a `PortfolioAggregationJob` for that portfolio and date, which acts as a trigger for the next stage.

2.  **Stage 2: Portfolio Time-Series Aggregation**
    * The **`AggregationScheduler`** in `portfolio_aggregation_service` is a background process that continuously polls the `portfolio_aggregation_jobs` table for pending work.
    * It has special logic to only claim a job for a given day `D` if the portfolio time-series for day `D-1` already exists, ensuring sequential processing.
    * Once a job is claimed, it publishes a `portfolio_aggregation_required` event to Kafka.
    * The **`PortfolioTimeseriesConsumer`** in `portfolio_aggregation_service` consumes this event, fetches all the necessary `position_timeseries` records for that day, and calls **`PortfolioTimeseriesLogic`** to perform the final aggregation and currency conversion, creating a single `portfolio_timeseries` record.

## 2. Adding a New Field to the Time-Series

If a new metric needs to be added to the `portfolio_timeseries` table (e.g., `total_turnover`), follow these steps:

1.  **Update the Data Model:** Add the new column (e.g., `total_turnover = Column(Numeric(18, 10))`) to the `PortfolioTimeseries` class.
    * **File:** `src/libs/portfolio-common/portfolio_common/database_models.py`

2.  **Generate a DB Migration:** Run the `alembic revision --autogenerate` command to create a migration script for the new column, then apply it with `alembic upgrade head`.

3.  **Update the Aggregation Logic:** Modify the `calculate_daily_record` method in the aggregation logic class to calculate the new value. This might require fetching additional data by adding a new method to the repository.
    * **File:** `src/services/portfolio_aggregation_service/app/core/portfolio_timeseries_logic.py`

4.  **Update the Repository:** Add the new field to the `upsert_portfolio_timeseries` method in the repository so that it is correctly written to the database during the `INSERT ... ON CONFLICT` operation.
    * **File:** `src/services/portfolio_aggregation_service/app/repositories/timeseries_repository.py`

5.  **Add Tests:** Add unit tests to `tests/unit/services/portfolio_aggregation_service/core/test_portfolio_timeseries_logic.py` to verify the new calculation.

## 3. Testing

To run the unit tests specifically for the time-series logic, use the following commands from the project root:
```bash
# For position-level logic
pytest tests/unit/services/timeseries_generator_service/timeseries-generator-service/core/test_position_timeseries_logic.py

# For portfolio-level logic
pytest tests/unit/services/portfolio_aggregation_service/core/test_portfolio_timeseries_logic.py
