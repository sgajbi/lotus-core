# CR-1627: Governed Kafka Terminal Recovery

Date: 2026-07-15
Issue: [#793](https://github.com/sgajbi/lotus-core/issues/793)
Status: Fixed locally; PR and exact-main proof pending

## Objective

Ensure one shared Kafka boundary owns terminal failure classification, confirmed DLQ publication,
support-evidence persistence, and source-offset commit. A terminal source message must remain
unacknowledged whenever any required recovery effect fails.

## Finding

`BaseConsumer` already implemented the governed terminal sequence, but twelve service call sites
called `_send_to_dlq_async(...)` inside `process_message` and returned normally. The shared run loop
interpreted that return as successful processing and could attempt its ordinary success commit even
when the local DLQ call returned `False`.

The pattern existed across portfolio derived state, valuation readiness, market-price
reprocessing, financial reconciliation, position valuation, and generic persistence consumers.
Service tests reinforced the defect by asserting direct protected-method calls rather than the
source commit invariant.

## Decision

Keep recovery policy in the existing shared runtime boundary:

1. delivery adapters decode and validate transport payloads,
2. adapters invoke application use cases,
3. transient infrastructure failures retain bounded retry classification,
4. terminal failures propagate with their original exception identity,
5. `BaseConsumer` publishes and confirms the DLQ record,
6. `BaseConsumer` persists source-safe support evidence,
7. only then may `BaseConsumer` commit the exact source message.

Do not add service-local recovery coordinators or another deployable. This is design modularity
inside the shared consumer boundary; no independent scale, security, ownership, or failure-isolation
requirement justifies more runtime topology.

## Same-Pattern Remediation

The migration removed every service-owned `_send_to_dlq_async(...)` call. The existing event-runtime
AST guard now permits direct publication only from:

- `BaseConsumer._recover_exhausted_retryable_failure`,
- `BaseConsumer._handle_terminal_processing_error`.

Any future service-level call fails `make event-runtime-contract-guard`.

## Scorecard

| Measure | Before | After |
| --- | ---: | ---: |
| Service-owned direct DLQ calls | 12 | 0 |
| Terminal DLQ/evidence/commit owners | shared base plus service adapters | shared base only |
| Validation exception identity | sometimes replaced by generic `ValueError` | preserved |
| Failed DLQ publication commit posture | service path could return as success | fail closed, no commit |
| Failed support-evidence commit posture | not proven through run loop | fail closed, no commit |
| Deterministic non-restoration guard | no | yes |
| Managed poison-message certification | no | yes |

## Compatibility

No event schema, topic, consumer group, API, OpenAPI, database, image identity, or downstream
contract changed. The intentional behavior correction is limited to terminal recovery: a source
offset is no longer eligible for ordinary success commit after a service-local DLQ attempt.

Retryable database and dependency failures retain their existing retry profiles. Position valuation
still records terminal job failure before raising; successful and idempotent paths are unchanged.

## Validation

- Signed commit `2bc698dab` migrated all affected adapters and behavior tests.
- Signed commit `df2e41af2` added deterministic DLQ ownership enforcement.
- Signed commit `c4f55eadd` proved support-evidence persistence failure leaves the source uncommitted.
- Signed commit `24d39a4c7` added the managed derived-state poison gate.
- Signed commit `bf9203b3c` aligned repo context, operator docs, wiki source, and recovery guidance.
- `41` focused service-consumer behavior tests passed.
- `66` shared `BaseConsumer` tests passed, including terminal success, publication failure, flush
  timeout, support-evidence failure, source commit failure, retry exhaustion, and failure budgets.
- `19` event-runtime guard tests and the executable guard passed.
- `8` recovery-module tests passed.
- Feature Lane `29412181517` passed lint, typecheck, architecture, OpenAPI, vocabulary, migration,
  security, warning, unit-db, and integration-lite jobs for `bf9203b3c`.
- Managed run `20260715T114232Z` produced exactly one DLQ record and one support event with
  `VALIDATION_ERROR`, then materialized exact valid snapshot/position/portfolio state in `4.144s`,
  returned source lag to zero, closed both job queues, reported zero reconciliation findings, and
  removed every run-owned container, network, and volume.

## Documentation Decision

Repository context, operator runbook, recovery navigation, dedicated recovery procedure, authored
wiki source, and this review ledger changed because the terminal execution contract and executable
certification flow are durable repository truth. API inventory and supported-feature declarations
did not change because no product API or supported business capability changed.

## Remaining Closure

Merge through the governed PR, rerun exact-main validation, publish wiki source, reconcile branch and
worktree state, then close #793 with QA evidence. Domain-safe partitioning and consumer concurrency
remain separately owned by #795.
