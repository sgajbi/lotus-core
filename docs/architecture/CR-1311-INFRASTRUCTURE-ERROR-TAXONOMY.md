# CR-1311 Infrastructure Error Taxonomy

## Scope

Issue cluster: GitHub issue #650.

This slice adds a shared infrastructure error taxonomy and applies it to representative Kafka and
database/audit adapter boundaries.

## Objective

Make infrastructure failures distinguishable by dependency, reason code, and retryability without
forcing application workflows to inspect raw SQLAlchemy, Kafka, or generic exception classes.

## Changes

1. Added `portfolio_common.infrastructure_errors`.
2. Re-exported ingestion audit write failure through the service-local compatibility module.
3. Added typed Kafka infrastructure errors to `EventPublishResult` for publish back-pressure,
   terminal publish failure, and uncertain delivery confirmation.
4. Preserved existing event-publish status and `error_message` fields for downstream compatibility.
5. Added focused tests for safe diagnostics and Kafka adapter mapping.
6. Added `docs/standards/infrastructure-error-taxonomy.md`.

## Behavior And Compatibility

No route path, request DTO, response DTO, OpenAPI metadata, repository SQL, database schema, Kafka
topic, Kafka key, Kafka header, event payload field, existing publish status, replay audit response,
metric name, runtime wiring, or deployment topology changed.

Existing callers can continue reading `EventPublishResult.status`, `error_message`, and
`undelivered_count`. New callers may read `infrastructure_error.safe_diagnostics()` for source-safe
operator diagnostics.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/libs/portfolio-common/test_event_publisher.py tests/unit/libs/portfolio-common/test_infrastructure_errors.py tests/unit/services/ingestion_service/services/test_ingestion_job_service_ports.py -q`
2. Scoped Ruff lint and format for the changed modules and tests.

Final architecture/wiki/diff evidence is recorded before commit.

## Documentation, Wiki, Context, And Skill Decision

Updated repo-local infrastructure error taxonomy documentation, codebase review ledger, and repo
context.

No wiki update is required because this slice changes internal adapter diagnostics, not
operator-facing route behavior or supported-feature truth.

No new platform skill change is required in this slice because the earlier platform skill update
already directs repeated issue patterns into ports/adapters, fake-port tests, guards, and context.

## Remaining Work

GitHub issue #650 is locally fixed for representative DB/audit and Kafka adapter error-translation
acceptance pending PR CI/QA and issue closure.

Future slices should map SQLAlchemy repository exceptions, downstream HTTP client failures,
cache failures, storage failures, and configuration failures into the same taxonomy as those
adapters are touched.
