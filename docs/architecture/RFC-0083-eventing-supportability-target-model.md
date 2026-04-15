# RFC-0083 Eventing And Supportability Target Model

This document is the RFC-0083 Slice 10 target model for event family governance,
observability posture, supportability APIs, operator diagnostics, and supportability evidence bundles
in `lotus-core`.

It does not change runtime event emission, Kafka topics, persistence, REST APIs, OpenAPI output, or
downstream contracts. It defines the governed catalog that later runtime and contract slices must use.

The executable helper is:

1. `src/libs/portfolio-common/portfolio_common/event_supportability.py`
2. `tests/unit/libs/portfolio-common/test_event_supportability.py`

## Target Principle

Events notify consumers that core truth or processing state changed. They must not become a substitute
for governed read contracts.

Downstream services should retrieve source truth through source-data products and evidence bundles.
Events provide:

1. change notification,
2. deterministic processing scope,
3. idempotent replay identity,
4. correlation and audit linkage,
5. supportability linkage to diagnostics and evidence.

## Event Families

Slice 10 classifies current and target event flows into these families:

| Family | Purpose |
| --- | --- |
| `source_ingestion_event` | Source facts accepted by ingestion adapters and sent toward persistence or orchestration |
| `domain_state_event` | Core state was persisted or calculated and a downstream stage may proceed |
| `pipeline_stage_event` | Internal processing stage readiness or completion |
| `reconciliation_control_event` | Reconciliation requested/completed and controls evaluated |
| `supportability_recovery_event` | Recovery, repair, replay, and DLQ lifecycle events |

The catalog currently records the event families that are already represented by shared Pydantic event
models in `portfolio_common.events`.

## Schema Governance

Every event family definition must declare:

1. event type,
2. schema model,
3. family,
4. direction,
5. aggregate type,
6. topic,
7. producer service,
8. consumer services,
9. idempotency requirement,
10. correlation requirement,
11. schema-version requirement,
12. supportability evidence bundle where applicable,
13. linked source-data products where applicable.

The helper validates duplicate event names, supported event families, supported directions, required
idempotency, required correlation, required schema versioning, evidence bundle names, consumer service
presence, source-data product names against the governed product catalog, and schema-model binding
against existing event model names when supplied by tests.

## Supportability Surfaces

Supportability surfaces are operator/control-plane surfaces, not business read products.

Current governed surfaces are:

| Surface | Service | Evidence |
| --- | --- | --- |
| `IngestionOperationsDiagnostics` | `event_replay_service` | `IngestionEvidenceBundle` |
| `ConsumerDlqReplay` | `event_replay_service` | `IngestionEvidenceBundle` |
| `CoreSupportLineage` | `query_control_plane_service` | `DataQualityCoverageReport` |
| `ReconciliationOperations` | `financial_reconciliation_service` | `ReconciliationEvidenceBundle` |

Every supportability surface must be operator-only and evidence-backed.
Supportability surface `route_family` values must use the same canonical RFC-0082 route-family
vocabulary as the route contract-family registry. The accepted Slice 10 values are
`Control-Plane And Policy` and `Control Execution`. Lower-case internal labels such as
`control_plane_and_policy` or `control_execution` are not valid in this catalog.

## Runtime Follow-Up

Future runtime slices must:

1. add explicit schema-version fields or envelope metadata where current event payloads do not carry
   them,
2. make correlation and idempotency visible in emitted events and replay evidence,
3. align Kafka topic names and outbox `event_type` values with the governed catalog,
4. emit or persist supportability recovery events where replay, DLQ, repair, or duplicate-blocking
   behavior changes,
5. expose operator diagnostics through supportability APIs rather than private database inspection,
6. keep downstream source retrieval on source-data products instead of event payload coupling.

## Validation

Slice 10 validation is:

1. `python -m pytest tests/unit/libs/portfolio-common/test_event_supportability.py -q`,
2. `python -m ruff check src/libs/portfolio-common/portfolio_common/event_supportability.py tests/unit/libs/portfolio-common/test_event_supportability.py --ignore E501,I001`,
3. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/event_supportability.py tests/unit/libs/portfolio-common/test_event_supportability.py`,
4. `git diff --check`,
5. `make lint`.
