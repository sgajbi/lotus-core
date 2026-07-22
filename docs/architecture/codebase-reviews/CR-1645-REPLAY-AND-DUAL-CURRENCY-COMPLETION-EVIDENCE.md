# CR-1645 Replay And Dual-Currency Completion Evidence

## Status

Final-head review corrections applied locally; request-safe exact-head Docker proof, protected PR
merge, and exact-main proof pending.

## Scope

GitHub issue #795 and Main Releasability run
[29892371749](https://github.com/sgajbi/lotus-core/actions/runs/29892371749): make
transaction replay and dual-currency E2E completion evidence reflect the runtime's governed,
request-safe completion contracts.

## Finding

The exact-main workflow failed in two evidence paths even though the adjacent static, unit,
integration, Docker smoke, latency, and fast performance jobs passed:

1. The first diagnosis treated global `transaction/duplicate` observations as interchangeable
   with completions for the repair requests issued by the profile. Review found that inference was
   unsafe: an unrelated at-least-once redelivery could increment the global duplicate metric and
   mask one missing repair. Canonical repair requests intentionally re-enter the unified financial
   flow, so this request-count gate must retain its incremental `transaction/processed` threshold
   unless future evidence is correlated to the individual requests.
2. The dual-currency fixture first declared readiness without every field later asserted. After
   that gap was fixed, final-head review found that non-null market values and zero unrealized P&L
   could still come from the query service's cost-basis continuity fallback while
   `valuation.market_price` remained absent. That predicate could therefore pass without proving
   the expected sell-date market-price snapshot.
3. Exact-head run `29899570356` exposed the actual replay-drain defect. Same-portfolio replay
   requests are correctly ordered onto one partition, but the
   shared concurrent consumer performed its full one-second idle poll while work was active on the
   paused busy partition. Although each replay publication completed in milliseconds, the loop
   added approximately 1.0-1.5 seconds between ordered messages and was still publishing the next
   30-record burst when the unchanged 180-second drain deadline expired.

The replay-storm failure was persistent in runs `29688109723`, `29719211821`,
`29802611218`, and `29892371749`. The dual-currency failure reproduced in the latest run as
one failure among 69 E2E tests.

## Remediation

1. Preserve the replay baseline and drain wait on the incremental
   `stage="transaction",outcome="processed"` count. Remove the speculative global
   processed-plus-duplicate helper and its tests so unrelated duplicate traffic cannot satisfy a
   request-count threshold.
2. Require the dual-currency fixture to observe the exact expected sell-date market price plus
   base/local market values and base/local unrealized P&L before yielding. Assert the market price
   in the scenario result as well as using it for readiness.
3. Bound Kafka polls to 100 milliseconds while concurrent processing tasks are active, while
   retaining the configured one-second idle poll. Preserve per-partition ordering, the governed
   in-flight limit, retry handling, and synchronous offset commits.
4. Scan the E2E suite for the same fallback-readiness pattern. The complex portfolio lifecycle used
   non-null unrealized P&L as its readiness signal, so it now requires its exact expected market
   price through the same reusable assertion helper. No other E2E poll predicate used this
   valuation-field pattern.

## Compatibility

No API, OpenAPI, event, database, migration, topic, partition, consumer-group, runtime topology,
timeout, or financial-calculation contract changes. The internal concurrent-consumer scheduler now
uses a bounded active-work poll so completed ordered work is drained promptly; idle polling,
ordering, capacity, retry, and commit contracts remain unchanged. Test and CI evidence semantics
retain request-safe processed-repair evidence and now measure complete dual-currency readiness.

## Validation

- `107` focused shared-consumer, replay-consumer, and performance-gate unit tests passed with
  warnings treated as errors after removing the rejected global duplicate-count implementation.
- `3` warning-strict valuation-readiness regression tests reject cost-basis fallback and wrong-price
  snapshots and accept the exact materialized snapshot; both affected E2E modules collect all `5`
  scenarios successfully.
- Scoped Ruff lint and format passed for all four touched Python files.
- The complete repository-native `make lint` pack passed again at signed head `2891f3c4d`. The pack
  includes ingestion, concurrency, observability, event-contract, and synthetic-fixture guards.
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
  Because that source head still allowed an unscoped duplicate count to satisfy the repair
  threshold, this run proves the scheduler and E2E behavior but is not final request-safe replay
  evidence.

## Remaining evidence

Run focused and repository-native static validation, commit and push the review correction, then
require final-head Feature Lane, protected PR Merge Gate, and exact-head Main Releasability with the
processed-only repair threshold. After protected merge, run exact-main Main Releasability, record
the no-wiki-change decision, update #795, and restore one clean Core worktree on synchronized
`main`.
