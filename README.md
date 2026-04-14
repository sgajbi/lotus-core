
# Lotus Core

This system provides a comprehensive suite of core portfolio services, including ingestion, persistence, position tracking, valuation, cashflow processing, timeseries generation, and simulation. It is designed as a distributed, event-driven architecture using Kafka for messaging and PostgreSQL for data persistence.

Platform architecture governance source:
- `https://github.com/sgajbi/lotus-platform` (cross-cutting and multi-service decisions)
- `REPOSITORY-ENGINEERING-CONTEXT.md` (repository-local engineering context and commands)

Local architecture direction and restructuring plan:
- `docs/RFCs/RFC 057 - Lotus Core Directory Reorganization and Legacy Module Retirement.md`
- `../lotus-platform/rfcs/RFC-0082-lotus-core-domain-authority-and-analytics-serving-boundary-hardening.md`
- `../lotus-platform/rfcs/RFC-0083-lotus-core-system-of-record-target-architecture.md`
- `docs/architecture/lotus-core-target-architecture.md`
- `docs/architecture/RFC-0082-contract-family-inventory.md`
- `docs/architecture/RFC-0083-target-state-gap-analysis.md`
- `docs/architecture/QUERY-SERVICE-AND-CONTROL-PLANE-BOUNDARY.md`
- `docs/standards/route-contract-family-registry.json`
- `docs/standards/layering-boundaries.md`
- `docs/standards/temporal-vocabulary.md`

Query-service PB/WM reporting contract guide:
- `docs/features/query_service/WEALTH-REPORTING-API-GUIDE.md`

## Table of Contents

- [Architectural Overview](#architectural-overview)
- [System Setup](#system-setup)
- [Running the System](#running-the-system)
- [Running Tests](#running-tests)
- [Verifying the Workflow](#verifying-the-workflow)
- [Code Quality](#code-quality)
- [Tools](#tools)

## Architectural Overview

The system follows a microservices architecture, where each service is responsible for a specific domain. Data flows through the system via Kafka topics, ensuring loose coupling and scalability.

### Core Data Flow

1.  **Ingestion Service**: Receives raw transaction and market data via a REST API and publishes it to Kafka.
2.  **Persistence Service**: Consumes raw data from Kafka and persists it to the PostgreSQL database.
3.  **Calculator Services**:
    * **Position Calculator**: Consumes persisted transactions, calculates position history, and manages reprocessing logic.
    * **Position Valuation Calculator**: Consumes price data and valuation jobs to calculate the market value of positions. It includes two key background tasks:
        * **ValuationScheduler**: Creates backfill valuation jobs, advances watermarks, and creates durable jobs for large-scale price reprocessing events.
        * **ReprocessingWorker**: Consumes the durable reprocessing jobs to fan-out watermark resets in a controlled, scalable manner, mitigating the "Thundering Herd" problem.
    * **Cashflow Calculator**: Calculates cash flows based on transactions.
4.  **Timeseries and Aggregation Services**: Materialize position-level and portfolio-level time series through explicit worker and aggregation boundaries.
5.  **Query Service**: Provides the operational read plane for foundational datasets such as portfolios, positions, transactions, prices, FX rates, instruments, lookups, and reporting-oriented source-data queries.
6.  **Query Control-Plane Service**: Provides governed downstream contract surfaces for analytics inputs, core snapshots, simulation sessions, integration policy, capabilities, support, lineage, and export lifecycles.
7.  **Event Replay and Financial Reconciliation Services**: Provide replay, DLQ, ingestion-health, reconciliation, and control-execution surfaces outside the ingestion write path.

### RFC-0082 Contract Families

Downstream-facing API ownership is governed by platform RFC-0082 and the local contract-family inventory:

- `docs/architecture/RFC-0082-contract-family-inventory.md`

The active families are:

1. `query_service`: operational reads.
2. `query_control_plane_service`: analytics inputs, snapshot/simulation, support, lineage, integration policy, and capability contracts.
3. `ingestion_service`: write ingress and adapter ingestion contracts.
4. `event_replay_service`: replay, DLQ, ingestion health, and operations control-plane contracts.
5. `financial_reconciliation_service`: reconciliation and control execution contracts.

`lotus-core` owns canonical source data and analytics inputs. It does not own downstream performance or risk analytics conclusions.

### RFC-0083 Target-State Gap Analysis

RFC-0083 is the master target architecture blueprint for hardening the current `lotus-core` into the
banking-grade system of record. The local Slice 0 implementation map is:

- `docs/architecture/RFC-0083-target-state-gap-analysis.md`

It identifies the current route, model, temporal, source-data product, ingestion, reconciliation,
security, and observability gaps that should drive the next implementation slices.

RFC-0083 Slice 1 temporal vocabulary and schema policy is documented in:

- `docs/standards/temporal-vocabulary.md`

RFC-0083 Slice 2 route family enforcement is documented in:

- `docs/standards/route-contract-family-registry.json`
- `scripts/route_contract_family_guard.py`

### Key Architectural Patterns

* **Event-Driven**: Services communicate asynchronously through events, promoting resilience and scalability.
* **Outbox Pattern**: Ensures atomicity between database writes and event publishing, guaranteeing "at-least-once" delivery.
* **Idempotent Consumers**: Consumers are designed to handle duplicate messages gracefully, preventing data corruption.
* **Durable Job Queues**: For high-volume, asynchronous tasks like reprocessing fan-outs, the system uses persistent database tables as durable queues to ensure reliability and control.

## System Setup

Follow these steps to set up the development environment.

### Prerequisites

* Docker and Docker Compose
* Python 3.11+
* Git Bash (on Windows)
* VSCode (recommended)

### Installation

1.  **Clone the Repository**:
    ```bash
    git clone <your-repository-url>
    cd lotus-core
    ```

2.  **Create a Virtual Environment**:
    ```bash
    py -3.12 -m venv .venv
    ```

3.  **Activate the Virtual Environment**:
    ```bash
    source .venv/Scripts/activate
    ```

4.  **Install Dependencies**:
    ```bash
    python -m pip install --upgrade pip
    make install
    ```

5.  **Set Up Environment Variables**:
    ```bash
    cp .env.example .env
    ```
    Review the `.env` file and ensure the settings are correct for your environment.

## Running the System

Canonical shared infrastructure ownership now lives in `lotus-platform`:

- shared local/platform baseline:
  - `C:\Users\Sandeep\projects\lotus-platform\platform-stack`

Use the local `lotus-core` compose stack when you specifically want an app-local or isolated-dev
environment for `lotus-core`.

Machine-readable compose contract:

- project name: `lotus-core-app-local`
- stack classification: `app-local`
- canonical shared infra owner: `lotus-platform/platform-stack`

1.  **Start App-Local Stack**:
    This command starts the local `lotus-core` app stack, including app-local Kafka, Zookeeper,
    PostgreSQL, Prometheus, `grafana`, all `lotus-core` services, and an automated one-shot demo
    data loader (`demo_data_loader`).
    ```bash
    docker compose up -d
    ```

    This stack is convenient for isolated development, but it is not the canonical owner of shared
    platform infrastructure for the rest of Lotus.

2.  **Set Up Kafka Topics**:
    This tool idempotently creates `lotus-core` domain topics. Topic definitions remain app-owned
    even when the canonical shared Kafka broker is started from `lotus-platform/platform-stack`.
    ```bash
    python -m tools.kafka_setup
    ```

3.  **Run Database Migrations**:
    Apply all pending database migrations to set up the schema.
    ```bash
    alembic upgrade head
    ```

4.  **Start Services**:
    Open a new terminal for each service to run them concurrently.
    ```bash
    # Terminal 1: Persistence Service
    python -m src.services.persistence_service.app.main

    # Terminal 2: Position Calculator Service
    python -m src.services.calculators.position_calculator.app.main

    # Terminal 3: Position Valuation Calculator Service
    python -m src.services.calculators.position_valuation_calculator.app.main

    # Terminal 4: Timeseries Generator Service
    python -m src.services.timeseries_generator_service.app.main

    # Terminal 5: Query Service (API)
    python -m src.services.query_service.app.main

    # Terminal 6: Query Control-Plane Service (integration, support, simulation)
    python -m src.services.query_control_plane_service.app.main

    # Terminal 7: Ingestion Service (API)
    python -m src.services.ingestion_service.app.main
    ```

## Running Tests

To run the enforced unit test gate:

```bash
make test
```

To run Docker/DB-backed unit tests explicitly:

```bash
make test-unit-db
```

To run the integration-lite suite used in CI coverage:

```bash
make test-integration-lite
```

Test suite composition is centrally managed in `scripts/test_manifest.py`.
Use this to inspect or validate exact CI test scope:

```bash
python scripts/test_manifest.py --suite integration-lite --print-args
python scripts/test_manifest.py --suite integration-lite --validate-only
```

To run the query-service unit suite directly:

```bash
pytest tests/unit/services/query_service -q
```

To run the fast local feature-lane parity gate:

```bash
make ci-local
```

To run the full pull-request merge gate locally:

```bash
make ci
```

To run the full main releasability gate locally:

```bash
make ci-main
```

To enforce ingestion endpoint documentation contract (`What/How/When` in OpenAPI descriptions):

```bash
make ingestion-contract-gate
```

To run architecture boundary checks:

```bash
make architecture-guard
```

To run the E2E smoke suite locally (requires Docker engine running):

```bash
make test-e2e-smoke
```

To run deterministic docker endpoint smoke (ingestion -> persistence -> query):

```bash
make test-docker-smoke
```

Optional deterministic controls:

```bash
# Reuse running stack without compose operations
python scripts/docker_endpoint_smoke.py --skip-compose

# Reset volumes for a clean-state deterministic run
python scripts/docker_endpoint_smoke.py --reset-volumes --build
```

## Verifying the Workflow

1.  **Ingest Data (Automated by Default)**:
    lotus-core now auto-loads a deterministic demo data pack during startup via Docker Compose.
    The `demo_data_loader` service ingests portfolios/instruments/transactions/prices/FX data
    and validates downstream query outputs.

    Check loader logs:

    ```bash
    docker compose logs --tail=200 demo_data_loader
    ```

    Optional controls:

    ```bash
    # Disable auto demo data pack loading for a run
    DEMO_DATA_PACK_ENABLED=false docker compose up -d

    # Run manually against a running stack
    python -m tools.demo_data_pack --ingestion-base-url http://core-ingestion.dev.lotus --query-base-url http://core-query.dev.lotus --query-control-plane-base-url http://core-query.dev.lotus
    ```

    The current flagship performance demo pack seeds:

    - portfolio: `DEMO_ADV_USD_001`
    - assigned benchmark: `BMK_GLOBAL_BALANCED_60_40` (`Global Balanced 60/40`)
    - alternate benchmark: `BMK_GLOBAL_GROWTH_80_20` (`Global Growth 80/20`)

    Verify benchmark discovery and assignment:

    ```bash
    curl -X POST "http://core-query.dev.lotus/integration/benchmarks/catalog" \
      -H "Content-Type: application/json" \
      -d '{"as_of_date":"2026-03-27","benchmark_currency":"USD","benchmark_status":"active","benchmark_type":"composite"}'

    curl -X POST "http://core-query.dev.lotus/integration/portfolios/DEMO_ADV_USD_001/benchmark-assignment" \
      -H "Content-Type: application/json" \
      -d '{"as_of_date":"2026-03-27"}'
    ```

    For UI/file-upload style onboarding, lotus-core also supports:

    ```bash
    curl -X POST "http://core-ingestion.dev.lotus/ingest/portfolio-bundle" \
      -H "Content-Type: application/json" \
      -d '{"mode":"UPSERT","businessDates":[],"portfolios":[],"instruments":[],"transactions":[],"marketPrices":[],"fxRates":[]}'
    ```

    For bulk CSV/XLSX onboarding with pre-validation:

    ```bash
    # Preview (validate only, no publishing)
    curl -X POST "http://core-ingestion.dev.lotus/ingest/uploads/preview" \
      -F "entityType=transactions" \
      -F "sampleSize=20" \
      -F "file=@./samples/transactions.csv"

    # Commit (strict by default; set allowPartial=true to publish valid rows only)
    curl -X POST "http://core-ingestion.dev.lotus/ingest/uploads/commit" \
      -F "entityType=transactions" \
      -F "allowPartial=true" \
      -F "file=@./samples/transactions.csv"
    ```

    For lotus-performance/lotus-manage style integration contracts, lotus-core query-service supports:

    ```bash
    curl "http://core-query.dev.lotus/integration/policy/effective?consumer_system=lotus-performance&tenant_id=default&include_sections=OVERVIEW&include_sections=HOLDINGS"

    curl "http://core-query.dev.lotus/integration/capabilities?consumer_system=lotus-gateway&tenant_id=default"
    ```

    Integration policy controls (optional):

    - `LOTUS_CORE_INTEGRATION_SNAPSHOT_POLICY_JSON`: policy object for section governance.
      Supports:
      - `strict_mode`
      - `consumers` (consumer -> allowed sections)
      - `tenants` (tenant overrides for `strict_mode`, `consumers`, `default_sections`)

    Integration capability policy overrides (optional):

    - `LOTUS_CORE_POLICY_VERSION`: default global policy version label.
    - `LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON`: tenant-scoped policy overrides used by
      `GET /integration/capabilities`.
      Supported keys per tenant:
      - `policy_version`
      - `features` (map of feature key -> boolean)
      - `workflows` (map of workflow key -> boolean override)
      - `supported_input_modes` (map of consumer system -> list, plus optional `default`)

    Example:

    ```bash
    export LOTUS_CORE_CAPABILITY_TENANT_OVERRIDES_JSON='{"tenant-a":{"policy_version":"tenant-a-v7","features":{"lotus_core.ingestion.bulk_upload":false},"supported_input_modes":{"lotus-performance":["lotus_core_ref"],"default":["lotus_core_ref"]}}}'
    ```

2.  **Query the API**:
    Once the services have processed the data, you can query the `query-service` API endpoints.

      * API Docs: `http://core-query.dev.lotus/docs`

3.  **Use Support and Lineage APIs (Preferred over direct DB access)**:
    Use the query-service operational APIs for support diagnostics.

    ```bash
    # Portfolio-level support overview
    curl "http://core-query.dev.lotus/support/portfolios/PORT001/overview"

    # Key-level lineage (epoch/watermark + latest artifacts)
    curl "http://core-query.dev.lotus/lineage/portfolios/PORT001/securities/SEC001"

    # Portfolio lineage key listing for support dashboards
    curl "http://core-query.dev.lotus/lineage/portfolios/PORT001/keys?reprocessing_status=CURRENT&skip=0&limit=100"

    # Valuation and aggregation support job queues
    curl "http://core-query.dev.lotus/support/portfolios/PORT001/valuation-jobs?status=PENDING&skip=0&limit=100"
    curl "http://core-query.dev.lotus/support/portfolios/PORT001/aggregation-jobs?status=PROCESSING&skip=0&limit=100"
    ```

## Code Quality

This project uses a lotus-manage-aligned engineering baseline:

```bash
make lint
make typecheck
make openapi-gate
make warning-gate
make check
make coverage-gate
make ci-local
make ci
make ci-main
```

`make check` enforces OpenAPI documentation quality for query-service endpoints:
- each business endpoint must define both `summary` and `description`
- each business endpoint must define `tags` and response contracts (including at least one `2xx` and one error response)
- duplicate `operationId` values are rejected
- `/health/*` endpoints are exempt

`make warning-gate` enforces warning-free unit execution (warning budget = `0`).

Active CI lane shape:

- `Remote Feature Lane`
- `Pull Request Merge Gate`
- `Main Releasability Gate`

`make ci` is the repository-native source of truth for the pull-request merge gate.
It includes dependency verification, contract guards, migration smoke, PR-grade
suite coverage, and the Docker-backed runtime gates that remain required before merge.

`make ci-main` extends `make ci` with the releasability-only gates:

- `Integration Full`
- `E2E Full`
- `Performance Load Gate (Full)`
- `Failure Recovery Gate`
- `Institutional Sign-Off Pack`

## Tools

The `tools/` directory contains helpful scripts for development:

  * `kafka_setup.py`: Creates Kafka topics.
  * `demo_data_pack.py`: Loads and validates a realistic multi-portfolio demo data pack.
  * `dlq_replayer.py`: Replays messages from a Dead Letter Queue.
  * `reprocess_tool.py`: Triggers reprocessing for specific transactions.

<!-- end list -->

 

 

## Platform Foundation Commands

- `make migration-smoke`
- `make migration-apply`
- `make security-audit`

Standards documentation:

- `docs/standards/migration-contract.md`
- `docs/standards/data-model-ownership.md`


