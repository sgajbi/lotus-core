# CR-1645 Replay And Dual-Currency Completion Evidence

## Status

Exact source-head Docker proof passed; final evidence commit, protected PR merge, and exact-main proof
pending.

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
3. Exact-head run `29899570356` proved the terminal-outcome correction was necessary but not
   sufficient. Same-portfolio replay requests are correctly ordered onto one partition, but the
   shared concurrent consumer performed its full one-second idle poll while work was active on the
   paused busy partition. Although each replay publication completed in milliseconds, the loop
   added approximately 1.0-1.5 seconds between ordered messages and was still publishing the next
   30-record burst when the unchanged 180-second drain deadline expired.

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
5. Bound Kafka polls to 100 milliseconds while concurrent processing tasks are active, while
   retaining the configured one-second idle poll. Preserve per-partition ordering, the governed
   in-flight limit, retry handling, and synchronous offset commits.
6. Scan the E2E suite for the same local-valuation readiness pattern. The exact mismatch was limited
   to `test_dual_currency_workflow.py`; other polling call sites do not assert the same four-field
   dual-currency contract.

## Compatibility

No API, OpenAPI, event, database, migration, topic, partition, consumer-group, runtime topology,
timeout, or financial-calculation contract changes. The internal concurrent-consumer scheduler now
uses a bounded active-work poll so completed ordered work is drained promptly; idle polling,
ordering, capacity, retry, and commit contracts remain unchanged. Test and CI evidence semantics
also now measure successful duplicate handling and complete dual-currency readiness truthfully.

## Validation

- `109` focused shared-consumer, replay-consumer, and performance-gate unit tests passed.
- Scoped Ruff lint and format passed for all four touched Python files.
- The complete repository-native `make lint` pack passed, including ingestion, concurrency,
  observability, event-contract, and synthetic-fixture guards.
- `make typecheck` passed across `237` source files.
- `make quality-wiki-docs-gate` passed; no repo-local wiki source changed because this slice does
  not alter operator-facing behavior or contracts.
- `git diff --check` passed.
- A local Docker-backed run was attempted but stopped before resource creation because Docker
  Desktop was unavailable after the host restart. No Compose project or cleanup action resulted.
- Exact-head Main Releasability run `29899570356` passed 20 jobs, including `E2E Full`; its full
  performance artifact passed steady (`37.151s`) and burst (`161.666s`) with zero added DLQ events,
  then exposed the active-poll latency in replay. This red run is diagnostic evidence only and is
  not merge evidence.
- Exact source-head Main Releasability run
  [`29902479829`](https://github.com/sgajbi/lotus-core/actions/runs/29902479829) passed all `22`
  jobs on `0d0fd96867c239dccb802cb0d44694d26c54d7a5`, including full E2E and downstream failure
  recovery. Artifact `20260722T083223Z-performance-load-gate.json` passed every unchanged full
  profile: steady drained `200` records in `14.099s`, burst drained `640` in `114.519s`, and the
  replay storm drained all `360` repair requests in `90.354s`; all profiles added zero DLQ events.
  Compared with diagnostic run `29899570356`, steady drain improved `62.05%`, burst improved
  `29.16%`, and replay moved from timeout to completion with `89.646s` of threshold headroom.

## Remaining evidence

Push this evidence-only commit and require final-head Feature Lane plus the protected PR Merge Gate.
After protected merge, run exact-main Main Releasability, record the no-wiki-change decision, update
#795, and restore one clean Core worktree on synchronized `main`.
