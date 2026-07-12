# CR-1394 Concurrency Duplicate-Delivery Proof Pack

## Objective

Fix GitHub issue #608 by making Core's idempotency, duplicate-delivery, outbox partial-delivery,
worker-claim, stale-reset, replay/live collision, and recalculation race evidence explicit,
deterministic, and guarded.

## Finding

Core already had several strong race protections: processed-event uniqueness fences, outbox claim
tokens and delivery-result accounting, `FOR UPDATE SKIP LOCKED` job claiming, epoch fences, and
stale-job reset predicates. The evidence was spread across unit and integration tests, and the
same-idempotency-key concurrent database path had no direct proof.

## Actions

- Added `docs/standards/concurrency-duplicate-delivery-test-pack.v1.json` to map the eight #608
  scenarios to concrete evidence, CI lane ownership, deterministic primitives, durable-state
  assertions, protected failure modes, and related remaining scopes.
- Added `scripts/concurrency_duplicate_delivery_guard.py` plus focused unit tests and wired
  `make concurrency-duplicate-delivery-guard` into `make lint`.
- Added a DB-backed processed-event race test proving concurrent claims of the same idempotency key
  create one `processed_events` row.
- Added a persistence adapter test proving representative transaction persistence consumers keep a
  semantic transaction idempotency key even when Kafka transport offsets differ.
- Updated testing strategy, risk matrix, repository context, wiki source, and this review ledger.

## Compatibility

No API route, DTO/OpenAPI schema, database schema, Kafka topic, event payload, runtime behavior, or
deployment topology changed. The slice adds tests and guardrails around existing behavior.

The proof pack intentionally leaves global semantic idempotency migration for every consumer family
to #553 and broader corporate-action/correction golden scenarios to #607.

## Validation

Run before commit:

- `python -m pytest tests/unit/scripts/test_concurrency_duplicate_delivery_guard.py -q`
- `python scripts/concurrency_duplicate_delivery_guard.py`
- `make concurrency-duplicate-delivery-guard`
- `python -m pytest tests/unit/services/persistence_service/adapters/test_persistence_event_adapter.py -q`
- DB-backed focused integration test for `tests/integration/libs/portfolio-common/test_idempotency_repository.py`
- scoped Ruff lint and format over the new guard/tests
- `make risk-based-test-coverage-matrix-guard`
- `make quality-wiki-docs-gate`
- `make lint`
- `git diff --check`

## Guidance Decision

Repo-local context, testing strategy, risk matrix, and wiki source changed because concurrency and
duplicate-delivery evidence is a durable Core contributor rule. No platform skill change is required
for this slice; the existing issue loop and backend delivery skills already require converting
repeated issue patterns into repo-native guards and context.
