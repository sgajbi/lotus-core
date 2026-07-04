# CR-1307 Ingestion Workflow Store Ports

## Scope

Issue cluster: GitHub issue #654.

This slice defines explicit store ports for representative ingestion idempotency and replay-audit
workflows.

## Objective

Reduce application-service coupling to SQLAlchemy session factories and helper functions for
audit/idempotency workflows while preserving existing API, persistence, and operator behavior.

## Changes

1. Added `IngestionJobStore` and `ReplayAuditStore` ports under
   `ingestion_service.app.ports`.
2. Added SQLAlchemy-backed adapters under `ingestion_service.app.adapters`.
3. Rewired `IngestionJobService.create_or_get_job`, replay-audit duplicate lookup, audit write,
   audit get, and audit list methods through injected store ports.
4. Preserved existing SQLAlchemy helper behavior as the default runtime implementation.
5. Added fake-store tests for idempotency replay versus conflict behavior and typed audit write
   failure propagation.
6. Added `scripts/ingestion_store_port_guard.py` and wired it into `make architecture-guard`.
7. Added `docs/standards/ingestion-workflow-store-port-standard.md`.

## Behavior And Compatibility

No route path, request DTO, response DTO, OpenAPI metadata, repository SQL, database schema, Kafka
topic, event payload, replay audit row field, idempotency conflict response, metric name, or
operator error code changed.

This is a design-modularity change inside the existing ingestion deployable. It is not a runtime
service split.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/services/ingestion_service/services/test_ingestion_job_service_ports.py tests/unit/services/ingestion_service/services/test_ingestion_replay_audits.py tests/unit/services/ingestion_service/services/test_ingestion_job_service_guardrails.py tests/unit/scripts/test_ingestion_store_port_guard.py -q`
   - 28 passed.
2. `python scripts/ingestion_store_port_guard.py`
   - Passed.
3. Scoped Ruff lint passed.
4. Scoped Ruff format passed.

Final architecture guard, wiki/docs gate, and diff evidence are recorded before commit.

## Documentation, Wiki, Context, And Skill Decision

Updated the codebase review ledger, repo-local engineering context, and ingestion workflow store
port standard.

No wiki update is required because this slice changes internal application-to-infrastructure
composition and testability, not operator commands, route behavior, supported features, or
published wiki truth.

No central Lotus skill change is required.

## Remaining Work

GitHub issue #654 is locally fixed for representative audit/idempotency store-port acceptance
criteria pending PR CI/QA and issue closure.

Follow-up issue slices should move the remaining ingestion diagnostics, DLQ event, operations mode,
repository unit-of-work, and publisher workflows behind their own capability-specific ports instead
of expanding `IngestionJobService` with more direct session-factory calls.

