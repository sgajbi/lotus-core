# CR-1645 Replay And Dual-Currency Completion Evidence

## Status

Fixed locally; Docker-backed PR and exact-main proof pending.

## Scope

GitHub issue #795 and Main Releasability run
[29892371749](https://github.com/sgajbi/lotus-core/actions/runs/29892371749): make
transaction replay and dual-currency E2E completion evidence reflect the runtime's governed
terminal contracts.

## Finding

The exact-main workflow failed in two evidence paths even though the adjacent static, unit,
integration, Docker smoke, latency, and fast performance jobs passed:

1. The full replay-storm profile publishes repeated repair deliveries for the same source
   transactions, but its drain probe counted only the `transaction/processed` metric. A delivery
   safely classified as `transaction/duplicate` is also terminal and permits the consumer offset
   to advance. Excluding that outcome made valid at-least-once deduplication indistinguishable from
   unfinished work.
2. The dual-currency fixture declared readiness when base-currency unrealized P&L became available,
   then asserted local market value and local unrealized P&L in a later test. The incomplete
   predicate allowed the test to read an intermediate response and intermittently convert
   `None` to `Decimal`.

The replay-storm failure was persistent in runs `29688109723`, `29719211821`,
`29802611218`, and `29892371749`. The dual-currency failure reproduced in the latest run as
one failure among 69 E2E tests.

## Remediation

1. Define one source-safe transaction-delivery completion count over the closed successful
   terminal set `processed|duplicate`.
2. Scrape both outcomes atomically through the existing bounded operation-evidence collector.
   Exclude rejected and failed outcomes so the gate cannot turn an invalid repair into a pass.
3. Make the replay baseline and drain wait use the successful terminal count without changing
   volume, timeout, partition count, concurrency, or idempotency behavior.
4. Require the dual-currency fixture to observe base/local market values and base/local unrealized
   P&L before yielding.
5. Scan the E2E suite for the same local-valuation readiness pattern. The exact mismatch was limited
   to `test_dual_currency_workflow.py`; other polling call sites do not assert the same four-field
   dual-currency contract.

## Compatibility

No API, OpenAPI, event, database, migration, topic, partition, consumer-group, runtime topology,
timeout, or financial-calculation contract changes. This slice changes only test and CI evidence
semantics so successful duplicate handling and complete dual-currency readiness are measured
truthfully.

## Validation

- `13` focused performance-gate unit tests passed.
- Scoped Ruff lint and format passed for all four touched Python files.
- The complete repository-native `make lint` pack passed, including ingestion, concurrency,
  observability, event-contract, and synthetic-fixture guards.
- `make typecheck` passed across `237` source files.
- `make quality-wiki-docs-gate` passed; no repo-local wiki source changed because this slice does
  not alter operator-facing behavior or contracts.
- `git diff --check` passed.
- A local Docker-backed run was attempted but stopped before resource creation because Docker
  Desktop was unavailable after the host restart. No Compose project or cleanup action resulted.

## Remaining evidence

Run Feature Lane and the full PR Merge Gate on the signed branch. The full performance and E2E jobs
must pass without changed timeout or capacity settings. After protected merge, run exact-main
Main Releasability, record the no-wiki-change decision, update #795, and restore one clean Core
worktree on synchronized `main`.
