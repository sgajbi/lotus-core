# CR-1333 Mapping Anti-Corruption Contract

## Objective

Complete the closure slice for GitHub issue #661 by turning the existing mapping boundary guidance
and representative mapper migrations into an executable architecture contract.

## Expected Improvement

Future API, ingestion, event, persistence, repository-output, and source-data changes now have one
contract index that verifies the representative anti-corruption artifacts stay present and that
selected inline mapping regressions do not return to orchestration or persistence repositories.

## Changes

1. Added `scripts/mapping_anti_corruption_guard.py`.
2. Added guard tests for the contract artifact, issue cross-links, ingestion DTO dump regression,
   and pipeline outbox serialization regression.
3. Wired `mapping-anti-corruption-guard` into `make architecture-guard` and scoped lint/format.
4. Linked the mapping boundary from the architecture index and named the guard in repo context.

## Compatibility Impact

No route path, request DTO, response DTO, OpenAPI metadata, Kafka topic, event type, payload field,
schema version, database schema, SQL query, repository method, metric name, runtime topology,
Dockerfile, package import path, or public behavior changed.

## No Runtime Split Decision

This is an in-process mapping and anti-corruption boundary. It does not create a new service, queue,
database, worker, scheduler, client contract, or deployment boundary.

## Documentation And Context Decision

Repo-local architecture and context were updated only as navigation to the executable contract.
No wiki source update is required because no operator workflow, public API, or reader-facing
supported capability changed.

## Validation Evidence

Focused validation was run before commit:

1. `python -m pytest tests/unit/scripts/test_mapping_anti_corruption_guard.py tests/unit/boundary_mapping/test_transaction_and_source_data_conformance.py -q`
2. `python scripts/mapping_anti_corruption_guard.py`
3. `python -m ruff check scripts/mapping_anti_corruption_guard.py tests/unit/scripts/test_mapping_anti_corruption_guard.py --ignore E501,I001`
4. `python -m ruff format --check scripts/mapping_anti_corruption_guard.py tests/unit/scripts/test_mapping_anti_corruption_guard.py`
5. `make architecture-guard`
6. `python scripts/wiki_validation_guard.py`
7. `git diff --check`
