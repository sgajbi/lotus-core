# CR-1396 Command API Behavior Certification

## Objective

Fix GitHub issue #605 by making command API behavior certification explicit, guarded, and tied to
route-surface tests for ingestion, replay, reconciliation, and long-running operations.

## Finding

Core already had meaningful command route tests, service tests, OpenAPI examples, idempotency
conflict tests, replay tests, and reconciliation authorization tests. The evidence was distributed,
and the route-level idempotency conflict path was not directly represented in the ingestion router
test harness. That made it easy for command endpoints to look tested while accepted, duplicate,
conflict, mode-blocked, retryable-failure, bookkeeping-failure, and security-denied semantics were
not visible as one certification surface.

## Actions

- Added `docs/standards/command-api-behavior-certification-pack.v1.json` for #605 scenarios.
- Added `scripts/command_api_behavior_certification_guard.py` and focused guard tests.
- Wired `make command-api-behavior-certification-guard` into `make lint`.
- Added a route-surface `/ingest/transactions` test for same idempotency key plus different
  payload returning `INGESTION_IDEMPOTENCY_CONFLICT`.
- Aligned the idempotency diagnostics integration fixture and OpenAPI example with the typed
  response contract, including payload fingerprint counts, payload conflict status, and stable
  reuse classification.
- Updated testing strategy, risk matrix, repository context, wiki source, and this ledger.

## Compatibility

No production runtime behavior, API route, DTO/OpenAPI schema, database schema, Kafka topic, event
payload, or deployment topology changed. The code-path adjustments are inside the integration test
harness so it mirrors existing production idempotency conflict semantics and current diagnostics
response fields. The OpenAPI example now matches the already declared response model.

## Validation

Run before commit:

- `python -m pytest tests/unit/scripts/test_command_api_behavior_certification_guard.py -q`
- `python scripts/command_api_behavior_certification_guard.py`
- `make command-api-behavior-certification-guard`
- `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -k "idempotency_replays_existing_job or rejects_same_idempotency_key_with_different_payload" -q`
- `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -k "idempotency_diagnostics_endpoint or idempotency_replays_existing_job or rejects_same_idempotency_key_with_different_payload" -q`
- `make test-ops-contract`
- scoped Ruff lint and format over the new guard/tests
- `make risk-based-test-coverage-matrix-guard`
- `make quality-wiki-docs-gate`
- `make lint`
- `git diff --check`

## Guidance Decision

Repo-local context changed because command API behavior certification is durable Core test truth.
No platform skill change is required for this slice; existing backend delivery and issue-loop
skills already require issue-derived patterns to become repo-native guards and context when
repeatable.
