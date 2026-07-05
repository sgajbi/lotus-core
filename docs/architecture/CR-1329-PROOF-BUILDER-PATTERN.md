# CR-1329 Proof Builder Pattern

## Objective

Fix GitHub issue #634 by introducing proof builders as an in-process evidence assembly pattern
before considering a separate proof service.

## Expected Improvement

Evidence-producing capabilities now have typed shared proof inputs and outputs for source-data
supportability, ingestion/replay evidence, reconciliation evidence, and app validation evidence.
The pattern keeps proof assembly out of routers, persistence models, repositories, and runbook-only
documentation while preserving current runtime topology.

## Changes

1. Added `portfolio_common.proof_builders` with typed proof inputs, observations, and artifacts.
2. Added focused unit tests that assemble proof artifacts without FastAPI, databases, Kafka, or
   downstream services.
3. Added `docs/standards/proof-builder-pattern-standard.md`.
4. Added `scripts/proof_builder_pattern_guard.py` with unit tests.
5. Wired `proof-builder-pattern-guard` into `make architecture-guard`.

## Compatibility Impact

No route path, request DTO, response DTO, OpenAPI metadata, Kafka topic, event payload, database
schema, repository SQL, metric name, runtime wiring, deployment topology, Dockerfile, package
import path, or public behavior changed.

## No Runtime Split Decision

This is an in-process design boundary. It does not create a proof service, database, queue, worker,
or deployable. A future runtime proof service requires the runtime-boundary decision process.

## Validation Evidence

Focused validation was run before commit:

1. `python -m pytest tests/unit/libs/portfolio-common/test_proof_builders.py tests/unit/scripts/test_proof_builder_pattern_guard.py -q`
2. `python scripts/proof_builder_pattern_guard.py`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/proof_builders.py scripts/proof_builder_pattern_guard.py tests/unit/libs/portfolio-common/test_proof_builders.py tests/unit/scripts/test_proof_builder_pattern_guard.py --ignore E501,I001`
4. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/proof_builders.py scripts/proof_builder_pattern_guard.py tests/unit/libs/portfolio-common/test_proof_builders.py tests/unit/scripts/test_proof_builder_pattern_guard.py`
5. `make architecture-guard`
6. `python scripts/wiki_validation_guard.py`
7. `git diff --check`
