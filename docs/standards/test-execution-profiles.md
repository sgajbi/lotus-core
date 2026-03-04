# Test Execution Profiles

## Goal

Run `unit`, `integration`, and `e2e` suites with isolated Docker resources so suites can execute in parallel without port or container collisions.

## Profiles

- `unit`
  - PostgreSQL: `55432`
  - Ingestion/Query: `8200` / `8201`
  - Kafka external/internal: `9092` / `9093`
- `integration`
  - PostgreSQL: `56432`
  - Ingestion/Query: `8300` / `8301`
  - Kafka external/internal: `9192` / `9193`
- `e2e`
  - PostgreSQL: `57432`
  - Ingestion/Query: `8400` / `8401`
  - Kafka external/internal: `9292` / `9293`

## How It Works

- `scripts/test_manifest.py` assigns a profile by suite:
  - `unit`, `unit-db` -> `unit`
  - integration and transaction contract suites -> `integration`
  - `e2e-smoke` -> `e2e`
- The runner exports:
  - `LOTUS_TEST_ENV_PROFILE`
  - suite-specific port variables
  - `COMPOSE_PROJECT_NAME=lotus-<profile>-<suite>`
- `tests/conftest.py` consumes these values and sets test URLs/DB defaults accordingly.
- `docker-compose.yml` uses environment-driven host port mappings and does not use fixed `container_name`.

## Commands

- Fast feedback: `make test-fast`
- Medium confidence: `make test-medium`
- Heavy gates: `make test-heavy`

These commands are intended to be composed in CI and locally depending on required confidence level.
