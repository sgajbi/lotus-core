# CR-1427: Calculator Event Owner Canonicalization

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Objective

Make the governed event catalog identify the real calculator and orchestrator deployables before
evaluating runtime consolidation. Pipeline ownership must not depend on retired logical aliases.

## Finding

The event supportability catalog still used `valuation_service`, `valuation_scheduler_service`,
and `position_timeseries_service`. Current runtime ownership belongs to
`position_valuation_calculator`, `valuation_orchestrator_service`,
`position_calculator_service`, and `timeseries_generator_service`.

The catalog validated event schema, topic, correlation, and idempotency posture, but it did not
prove that producer and consumer names existed in the governed runtime-boundary catalog.

## Change

- Replaced retired event actors with current deployable service identifiers.
- Added event-owner validation against `runtime-boundary-decision-catalog.json`.
- Preserved `BaseConsumer` as the one governed technical actor for shared DLQ publication.
- Updated the RFC-0083 direct valuation-job topic table.
- Added regression coverage that rejects a retired `valuation_service` actor.

## Compatibility

No Kafka topic, event type, payload, header, consumer group, idempotency key, database schema,
runtime topology, route, or OpenAPI contract changed. This corrects governance metadata only.

## Evidence

- `python -m pytest tests/unit/scripts/test_event_runtime_contract_guard.py tests/unit/libs/portfolio-common/test_event_supportability.py -q` -> 36 passed.
- `python scripts/quality/event_runtime_contract_guard.py` -> passed.
- Scoped Ruff lint and format checks -> passed.
- `git diff --check` -> passed.

## Same-Pattern Decision

The scan covered every producer and consumer in the event-family and direct-Kafka catalogs. No
other retired service actor remains on those governed surfaces.

No README or wiki change is required because their current architecture pages already use the
canonical deployable names. Repository context will be updated with the final #468 stage-boundary
and consolidation decision rather than for this metadata-only correction.
