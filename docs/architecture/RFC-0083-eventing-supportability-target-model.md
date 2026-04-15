# RFC-0083 Eventing And Supportability Target Model

This document is the RFC-0083 Slice 10 target model for event family governance,
observability posture, supportability APIs, operator diagnostics, and supportability evidence bundles
in `lotus-core`.

It does not change runtime event emission behavior, Kafka topics, persistence, REST APIs, OpenAPI
output, or downstream contracts. It defines the governed catalog that later runtime and contract slices
must use, and adds runtime contract proof that current outbox `event_type` and topic pairs remain
aligned with that catalog.

The executable helper is:

1. `src/libs/portfolio-common/portfolio_common/event_supportability.py`
2. `tests/unit/libs/portfolio-common/test_event_supportability.py`
3. `scripts/event_runtime_contract_guard.py`
4. `tests/unit/scripts/test_event_runtime_contract_guard.py`
5. `src/libs/portfolio-common/portfolio_common/events.py`
6. `src/libs/portfolio-common/portfolio_common/outbox_repository.py`
7. `tests/unit/libs/portfolio-common/test_outbox_repository.py`

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

The runtime contract guard parses source files for literal `OutboxRepository.create_outbox_event(...)`
calls and outbox-details dictionaries. Every discovered runtime `event_type` and topic pair must exist
in the event supportability catalog with the same topic. This catches accidental Kafka topic drift,
renamed outbox event types, or new emissions that bypass governance. Payload envelope proof is owned by
the centralized outbox repository tests because that repository constructs the emitted Kafka payload.

`OutboxRepository` now centrally enriches emitted payloads with governed envelope metadata:

1. `event_type`,
2. `schema_version`,
3. `correlation_id`.

The repository rejects payload metadata that conflicts with the outbox row metadata. Producers should
continue passing domain payloads and let the repository add the supportability envelope; this keeps
event metadata consistent without duplicating envelope code in each service.

All shared event models inherit from `CoreEventModel`, which keeps `from_attributes=True` and
explicitly ignores extra fields. This makes event consumers intentionally tolerant of the governed
outbox envelope metadata instead of relying on implicit Pydantic defaults.

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
Supportability surface evidence bundles must also resolve to RFC-0083 Slice 9 operator-only security
profiles, keeping operator diagnostics aligned with the source-data product security model.

## Runtime Follow-Up

Future runtime slices must:

1. keep schema-version envelope metadata centralized in `OutboxRepository`,
2. make idempotency visible in emitted events and replay evidence,
3. keep Kafka topic names and outbox `event_type` values aligned with the guarded catalog,
4. emit or persist supportability recovery events where replay, DLQ, repair, or duplicate-blocking
   behavior changes,
5. expose operator diagnostics through supportability APIs rather than private database inspection,
6. keep downstream source retrieval on source-data products instead of event payload coupling.

## Validation

Slice 10 validation is:

1. `python scripts/event_runtime_contract_guard.py`,
2. `python -m pytest tests/unit/libs/portfolio-common/test_event_supportability.py tests/unit/libs/portfolio-common/test_outbox_repository.py tests/unit/scripts/test_event_runtime_contract_guard.py -q`,
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/event_supportability.py src/libs/portfolio-common/portfolio_common/events.py src/libs/portfolio-common/portfolio_common/outbox_repository.py scripts/event_runtime_contract_guard.py tests/unit/libs/portfolio-common/test_event_supportability.py tests/unit/libs/portfolio-common/test_outbox_repository.py tests/unit/scripts/test_event_runtime_contract_guard.py --ignore E501,I001`,
4. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/event_supportability.py src/libs/portfolio-common/portfolio_common/events.py src/libs/portfolio-common/portfolio_common/outbox_repository.py scripts/event_runtime_contract_guard.py tests/unit/libs/portfolio-common/test_event_supportability.py tests/unit/libs/portfolio-common/test_outbox_repository.py tests/unit/scripts/test_event_runtime_contract_guard.py`,
5. `git diff --check`,
6. `make lint`.
