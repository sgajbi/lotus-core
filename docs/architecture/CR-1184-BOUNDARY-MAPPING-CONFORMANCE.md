# CR-1184 Boundary Mapping Conformance

## Objective

Begin GitHub issues #665 and #661 by adding a discoverable boundary-mapping conformance suite and
extracting the transaction event-to-persistence-record mapping into an explicit function.

## Expected Improvement

- Transaction event persistence values now come from a named mapper instead of inline repository
  dictionary construction.
- Boundary tests prove representative transaction and source-data mappings preserve identifiers,
  dates, Decimal precision, currency normalization, source lineage, schema version, correlation ID,
  event type, supportability, and product envelope identity.
- Unknown and missing transaction event fields are covered by the mapper conformance suite.
- A repo-native `make test-boundary-mapping-conformance` command makes the suite easy to run and
  include in PR evidence.

## Changes

- Added `transaction_event_to_record_values(...)` in
  `persistence_service.app.repositories.transaction_db_repo`.
- Routed `TransactionDBRepository.create_or_update_transaction(...)` through the mapper.
- Added `tests/unit/boundary_mapping/test_transaction_and_source_data_conformance.py`.
- Added the `boundary-mapping-conformance` test-manifest suite and Make target.
- Added `mapping-anti-corruption-boundary.md` as the repo-local mapping standard.
- Updated `REPOSITORY-ENGINEERING-CONTEXT.md`, the codebase review ledger, and quality reports.

## Compatibility

No API route, Kafka topic, database schema, public DTO, or successful persistence behavior changed.
The transaction repository still excludes fee component fields from transaction table values. The
new mapper also explicitly excludes event envelope metadata (`event_type`, `schema_version`, and
`correlation_id`) because those fields are not transaction table columns.

## Validation

- `python -m pytest tests/unit/boundary_mapping/test_transaction_and_source_data_conformance.py tests/unit/services/persistence_service/repositories/test_transaction_db_repository.py -q`
- `make test-boundary-mapping-conformance`
- `python scripts/test_manifest.py --suite boundary-mapping-conformance --validate-only`
- `python -m ruff check tests/unit/boundary_mapping/test_transaction_and_source_data_conformance.py src/services/persistence_service/app/repositories/transaction_db_repo.py scripts/test_manifest.py`

## Documentation And Wiki Decision

Updated architecture docs, repository context, codebase review ledger, and quality reports because a
new repo-native conformance command and mapping boundary policy were introduced. No wiki source
update is required because no operator workflow, public API contract, or user-facing runtime
behavior changed.

## Follow-Up

Issues #661 and #665 remain open for broader API DTO-to-command mappers, typed read records,
Kafka/event adapter mappers, additional source-data product envelopes, architecture guard coverage,
and CI evidence after the branch is pushed.
