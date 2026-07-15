# Developer's Guide: Timeseries Generation and Portfolio Aggregation

This guide explains how to extend the current two-stage derived-state pipeline without crossing its
delivery, application, domain, port, and infrastructure boundaries.

## 1. Architecture Overview

The platform is designed as a two-stage pipeline to transform daily snapshots into the final, aggregated time-series data used for analytics.

1.  **Stage 1: Position Time-Series Generation**
    * The **`PositionTimeseriesConsumer`** in `timeseries_generator_service` validates and maps `valuation.snapshot.persisted` events.
    * **`MaterializePositionTimeseries`** loads immutable source records through a repository port, invokes **`PositionTimeseriesLogic`**, and performs bounded backdated propagation.
    * Its SQLAlchemy adapter atomically persists `position_timeseries` rows and idempotently stages a portfolio aggregation job for each affected portfolio date.

2.  **Stage 2: Portfolio Time-Series Aggregation**
    * The **`AggregationScheduler`** in `portfolio_aggregation_service` is a background process that continuously polls the `portfolio_aggregation_jobs` table for pending work.
    * It has special logic to only claim a job for a given day `D` if the portfolio time-series for day `D-1` already exists, ensuring sequential processing.
    * Once a job is claimed, it publishes a `portfolio_day.aggregation.job.requested` event to Kafka.
    * The **`PortfolioTimeseriesConsumer`** in `portfolio_aggregation_service` validates and maps the event to **`MaterializePortfolioTimeseries`**. The application use case loads the target epoch and position-timeseries inputs through typed ports, invokes the calculation policy, releases the durable job claim, and atomically stages the `portfolio_timeseries` output plus completion/reconciliation events through a SQLAlchemy/outbox unit of work.

## 2. Adding a New Field to the Time-Series

If a new metric needs to be added to the `portfolio_timeseries` table (e.g., `total_turnover`), follow these steps:

1.  **Update the Data Model:** Add the new column (e.g., `total_turnover = Column(Numeric(18, 10))`) to the `PortfolioTimeseries` class.
    * **File:** `src/libs/portfolio-common/portfolio_common/database_models.py`

2.  **Generate a DB Migration:** Run the `alembic revision --autogenerate` command to create a migration script for the new column, then apply it with `alembic upgrade head`.

3.  **Update Domain Arithmetic:** Extend the pure `calculate_portfolio_timeseries` function. Keep SQLAlchemy, market-data reads, logging, and framework objects out of this module.
    * **File:** `src/services/portfolio_aggregation_service/app/domain/portfolio_timeseries/calculator.py`

4.  **Update Source Enrichment When Required:** If the metric requires instrument or FX data, extend the typed port and source-enrichment application service without moving I/O into domain arithmetic.
    * **File:** `src/services/portfolio_aggregation_service/app/application/portfolio_timeseries/calculation.py`

5.  **Update Persistence:** Add the field to `PortfolioAggregationRepository.upsert_portfolio_timeseries` so it is written by the existing idempotent upsert.
    * **File:** `src/services/portfolio_aggregation_service/app/infrastructure/portfolio_aggregation_repository.py`

6.  **Add Tests:** Put pure arithmetic and invariants under the domain test package. Put market-data resolution, normalization, caching, and source-failure cases under the application test package.

## 3. Testing

To run the unit tests specifically for the time-series logic, use the following commands from the project root:
```bash
# For position-level logic
python -m pytest tests/unit/services/timeseries_generator_service -q

# For portfolio aggregation application and domain behavior
python -m pytest tests/unit/services/portfolio_aggregation_service -q
```
