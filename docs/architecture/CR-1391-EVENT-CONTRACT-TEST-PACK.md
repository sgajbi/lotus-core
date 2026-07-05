# CR-1391 Event Contract Test Pack

## Objective

Fix GitHub issue `sgajbi/lotus-core#604` by making Kafka and outbox event contract evidence
repo-owned, catalog-backed, and CI-visible instead of spread across incidental tests.

## Findings

Core already had an event supportability catalog and unknown-field rejection, but the event contract
evidence was not organized per governed topic and event version. The shared Kafka validation helper
also allowed callers to validate only the Pydantic body shape, which meant a consumer could miss
missing `event_type`, missing `schema_version`, or unsupported schema-version drift unless it added
local checks.

## Actions Taken

1. Added `docs/standards/event-contract-test-pack.v1.json` covering every current
   `EVENT_FAMILY_DEFINITIONS` and `DIRECT_KAFKA_TOPIC_DEFINITIONS` entry.
2. Added `scripts/event_contract_test_pack_guard.py` and
   `tests/unit/scripts/test_event_contract_test_pack_guard.py`.
3. Wired `make event-contract-test-pack-guard` into `make lint`.
4. Centralized the governed event schema version in `portfolio_common.events`.
5. Extended `validate_kafka_event_payload(...)` with optional expected-event-type and accepted
   schema-version checks, then adopted it in current governed event-family consumers.
6. Updated the risk-based test coverage matrix and testing strategy.

## Compatibility

Valid produced events keep the same topics, payload fields, outbox envelope metadata, database
schema, and runtime topology. The intentional behavior change is stricter rejection for governed
consumer paths that declare an expected event type: missing `event_type`, missing `schema_version`,
unsupported schema versions, or wrong event types now fail before use-case handling and follow the
existing DLQ path.

## Validation Evidence

Focused evidence is recorded in the issue comment and commit:

1. event-mapping contract tests,
2. current governed consumer fixture tests,
3. event-contract test-pack guard tests,
4. direct guard execution,
5. scoped Ruff lint/format,
6. docs/quality guard.

## Guidance Decision

Repo-local context and testing strategy changed because the issue exposed repeatable event-contract
drift risk. No platform-wide skill change is required for this slice; the reusable rule is
repo-specific and now has deterministic enforcement. No wiki source changed because no operator
workflow, support runbook, or public documentation path changed.
