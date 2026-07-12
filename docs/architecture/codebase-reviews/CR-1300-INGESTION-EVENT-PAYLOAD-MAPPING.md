# CR-1300 Ingestion Event Payload Mapping

## Scope

Issue cluster: GitHub issue #661, with supporting cross-links to #640 and #648.

This slice closes the remaining representative API DTO to event-payload mapping gap in the
`lotus-core` mapping and anti-corruption boundary.

## Objective

Remove direct DTO serialization from ingestion publish workflows and make the raw ingestion event
payload boundary explicit, typed, and directly testable before Kafka publication.

## Changes

1. Added `ingestion_event_payloads.py` for named API DTO to raw-event-payload mapping helpers.
2. Rewired business-date, portfolio, transaction, instrument, market-price, and FX-rate publish
   methods through the mapper helpers instead of inline `model_dump()` calls.
3. Added direct mapper tests for transaction identifiers, dates, Decimals, currency
   normalization, source lineage, fee aggregation, reference dates, and FX-rate Decimal fidelity.
4. Extended the boundary conformance test so the published transaction payload is proven to come
   from the explicit ingestion payload mapper before Kafka/event/persistence mapping continues.

## Behavior And Compatibility

This is a design-modularity slice inside the existing `ingestion_service` deployable. It is not a
runtime service split.

No route path, request DTO, response DTO, OpenAPI metadata, Kafka topic, Kafka key, Kafka header,
published payload field, payload value type, idempotency behavior, correlation propagation,
metrics increment, batch failure accounting, or flush behavior changed.

## Validation Evidence

Focused local validation before docs update:

1. `python -m pytest tests\unit\services\ingestion_service\services\test_ingestion_event_payloads.py tests\unit\services\ingestion_service\services\test_ingestion_service.py tests\unit\boundary_mapping\test_transaction_and_source_data_conformance.py -q`
   - 21 passed, 1 existing warning from a `model_construct(...)` invalid-internal-object guard.
2. `python -m ruff check --fix tests\unit\boundary_mapping\test_transaction_and_source_data_conformance.py`
   - fixed import ordering after the conformance assertion was added.

Final scoped validation is recorded in the commit evidence after the full slice gates run.

## Documentation, Wiki, Context, And Skill Decision

Updated the mapping/anti-corruption boundary, codebase review ledger, and repo-local engineering
context.

No wiki update is required because no operator command, API route behavior, runtime support
workflow, user-facing capability, or published wiki truth changed.

No central Lotus skill change is required. The repeatable guidance is repo-local and now says
ingestion publish workflows should use explicit payload mappers instead of inline DTO dumps.

## Remaining Work

GitHub issue #661 is locally fixed for the representative mapping-contract acceptance set pending
PR CI/QA and issue closure. Future API DTO to application-command/result paths should follow the
same anti-corruption pattern when they change, especially older router handlers that still assemble
command payloads inline.
