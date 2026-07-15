# Developer's Guide: Timeseries Generation and Portfolio Aggregation

This guide explains how to extend the two-stage derived-state capability without crossing its
delivery, application, domain, port, and infrastructure boundaries.

## 1. Architecture Overview

One deployable contains two explicit module flows.

1.  **Stage 1: Position Time-Series Generation**
    * `delivery/valuation_snapshots/PositionTimeseriesConsumer` validates and maps
      `valuation.snapshot.persisted` events.
    * `MaterializePositionTimeseries` loads immutable source records through a repository port,
      invokes `calculate_position_timeseries`, and performs bounded backdated propagation.
    * Its SQLAlchemy adapter atomically persists `position_timeseries` rows and idempotently stages a portfolio aggregation job for each affected portfolio date.

2.  **Stage 2: Portfolio Time-Series Aggregation**
    * `AggregationScheduler` polls `portfolio_aggregation_jobs` for eligible work.
    * It has special logic to only claim a job for a given day `D` if the portfolio time-series for day `D-1` already exists, ensuring sequential processing.
    * A claim records owner, token, and UTC expiry. Bounded workers invoke
      `MaterializePortfolioTimeseries` directly through framework-neutral commands.
    * Terminal writes require the same job ID, lease token, and `PROCESSING` state. The unit of work
      atomically writes output and stages completion/reconciliation events.

## 2. Adding a New Field to the Time-Series

If a new metric needs to be added to the `portfolio_timeseries` table (e.g., `total_turnover`), follow these steps:

1.  **Update the Data Model:** Add the new column (e.g., `total_turnover = Column(Numeric(18, 10))`) to the `PortfolioTimeseries` class.
    * **File:** `src/libs/portfolio-common/portfolio_common/database_models.py`

2.  **Generate a DB Migration:** Run the `alembic revision --autogenerate` command to create a migration script for the new column, then apply it with `alembic upgrade head`.

3.  **Update Domain Arithmetic:** Extend the pure `calculate_portfolio_timeseries` function. Keep SQLAlchemy, market-data reads, logging, and framework objects out of this module.
    * **File:** `src/services/portfolio_derived_state_service/app/domain/portfolio_timeseries/calculator.py`

4.  **Update Source Enrichment When Required:** If the metric requires instrument or FX data, extend the typed port and source-enrichment application service without moving I/O into domain arithmetic.
    * **File:** `src/services/portfolio_derived_state_service/app/application/portfolio_timeseries/calculation.py`

5.  **Update Persistence:** Add the field to `PortfolioAggregationRepository.upsert_portfolio_timeseries` so it is written by the existing idempotent upsert.
    * **File:** `src/services/portfolio_derived_state_service/app/infrastructure/portfolio_aggregation_repository.py`

6.  **Add Tests:** Put pure arithmetic and invariants under the domain test package. Put market-data resolution, normalization, caching, and source-failure cases under the application test package.

## 3. Testing

To run the unit tests specifically for the time-series logic, use the following commands from the project root:
```bash
# Position and portfolio application/domain/adapters plus runtime supervision
python -m pytest tests/unit/services/portfolio_derived_state_service -q

# PostgreSQL repository and lease-fencing behavior
python -m pytest tests/integration/services/portfolio_derived_state_service -q
```
