# CR-1431: Transaction Event Anti-Corruption Boundary

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Objective

Stop the combined transaction-processing application/domain layers from consuming the Pydantic
Kafka event model directly.

## Change

- Added immutable, framework-neutral `BookedTransaction` covering all 98 transaction business
  fields.
- Added `ProcessTransactionCommand` and typed event/idempotency metadata.
- Added a Kafka delivery mapper with deterministic event-to-domain and domain-to-event conversion.
- Added a field-completeness contract that fails fast when the governed event or domain model
  drifts.
- Added an architecture rule blocking `portfolio_common.events` imports from the target domain and
  application packages.

## Compatibility

No event schema, validation, normalization, topic, consumer group, payload, database model,
calculation, runtime wiring, image, route, or OpenAPI contract changed. The round-trip test proves
normalized currencies, envelope metadata, linked component/dependency collections, and all other
current event values are preserved.

## Evidence

- Mapper/domain tests plus architecture guard tests -> 23 passed.
- Focused mypy -> passed for seven source files.
- Strict architecture boundary guard -> passed.
- Scoped Ruff lint/format -> passed.
- Targeted and full source Vulture scans at 80% confidence -> no findings.
- `git diff --check` -> passed.

## Same-Pattern Decision

The event/domain field-set equality test covers the complete `TransactionEvent`, so future fields
cannot be silently omitted. Other governed event families remain outside this issue's combined
transaction-processing scope.

No README or wiki change is required because runtime topology and operator behavior did not change.
Repository context and the application command/result standard were updated because this is a
durable agent and architecture rule. No central skill change is required.
