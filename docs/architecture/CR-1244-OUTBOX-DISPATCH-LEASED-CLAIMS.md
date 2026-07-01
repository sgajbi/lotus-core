# CR-1244 Outbox Dispatch Leased Claims

Date: 2026-07-01

## Objective

Fix GitHub issue #580 by preventing the outbox dispatcher from holding database row locks while
waiting on Kafka publish and flush callbacks.

## Finding

`OutboxDispatcher._process_batch_sync()` selected `PENDING` outbox rows with
`FOR UPDATE SKIP LOCKED` and then called Kafka publish, flush, and result persistence while still
inside the same database transaction. Kafka slowdown could therefore extend the database
transaction and row-lock lifetime for the selected outbox rows.

## Change

- Added nullable internal `claim_token` and `claim_expires_at` fields to `outbox_events`.
- Added an Alembic migration and hot-path indexes for claim eligibility and fenced result updates.
- Refactored the dispatcher into:
  1. a short claim transaction that assigns a per-batch claim token and lease,
  2. Kafka publish and flush outside the database transaction,
  3. a short result transaction that only updates rows still carrying the matching claim token.
- Added configurable `OUTBOX_DISPATCHER_CLAIM_LEASE_SECONDS` with a 60-second default.
- Cleared claim fields on successful, retryable-failure, and terminal-failure result updates.

## Expected Improvement

- Kafka broker latency no longer extends the row locks taken by outbox claim selection.
- Concurrent dispatchers skip actively leased rows and can reclaim expired claims.
- Stale delivery callbacks from a dispatcher that lost its claim cannot overwrite a row reclaimed by
  another worker.
- The pattern is now explicit and reusable for future claim-and-publish loops: short claim,
  publish outside lock, fenced result update, lease-based reclaim.

## Behavior And Compatibility

- Existing API routes, OpenAPI contracts, Kafka topics, outbox payloads, event headers, and consumer
  contracts are preserved.
- Database schema changes are additive and nullable.
- The intentional runtime behavior change is internal: claimed `PENDING` rows carry a temporary
  claim token/expiry, and result updates are ignored if the claim token no longer matches.
- No wiki update is required because no operator command or public runbook changed.

## Tests Added Or Extended

- Added integration coverage proving Kafka publish observes a committed claim before publish and
  that success clears the claim.
- Added integration coverage proving expired claims are reclaimed.
- Added integration coverage proving stale success callbacks do not update rows after the claim is
  replaced.
- Extended partial-delivery, synchronous-publish-failure, null-retry, and flush-timeout tests to
  assert claim cleanup after result persistence.
- Extended outbox runtime settings tests for the claim lease default, environment override, local
  fallback, and constructor override.

## Validation Evidence

- `python -m pytest tests/unit/libs/portfolio-common/test_outbox_dispatcher.py -q --tb=short`
  - Result: `10 passed`.
- `python -m pytest tests/integration/libs/portfolio-common/test_outbox_dispatcher.py tests/integration/libs/portfolio-common/test_outbox_dispatcher_delivery_results.py -q --tb=short`
  - Result after rebuilding the local Docker image so container-side migrations saw the new working
    tree migration: `17 passed`.
- `python -m ruff check src/libs/portfolio-common/portfolio_common/outbox_settings.py src/libs/portfolio-common/portfolio_common/database_models.py src/libs/portfolio-common/portfolio_common/outbox_dispatcher.py tests/unit/libs/portfolio-common/test_outbox_dispatcher.py tests/integration/libs/portfolio-common/test_outbox_dispatcher.py tests/integration/libs/portfolio-common/test_outbox_dispatcher_delivery_results.py alembic/versions/c1009d0e1f2a3_feat_add_outbox_dispatch_claim_lease.py --ignore E501,I001`
  - Result: passed.
- `python -m ruff format --check src/libs/portfolio-common/portfolio_common/outbox_settings.py src/libs/portfolio-common/portfolio_common/database_models.py src/libs/portfolio-common/portfolio_common/outbox_dispatcher.py tests/unit/libs/portfolio-common/test_outbox_dispatcher.py tests/integration/libs/portfolio-common/test_outbox_dispatcher.py tests/integration/libs/portfolio-common/test_outbox_dispatcher_delivery_results.py alembic/versions/c1009d0e1f2a3_feat_add_outbox_dispatch_claim_lease.py`
  - Result: passed.
- `python -m mypy --config-file mypy.ini src/libs/portfolio-common/portfolio_common/outbox_settings.py src/libs/portfolio-common/portfolio_common/outbox_dispatcher.py`
  - Result: passed.
- `make migration-smoke`
  - Result: passed; `c1009d0e1f2a3` is the single Alembic head.

## Remaining Work

- Keep issue #580 open for PR, CI, and QA evidence.
- Use the leased-claim/fenced-result pattern for future outbox or direct publish loops that claim
  durable work before broker interaction.
