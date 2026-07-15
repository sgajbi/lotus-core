# CR-1626: Portfolio Derived-State Runtime Consolidation

Date: 2026-07-15
Issue: [#714](https://github.com/sgajbi/lotus-core/issues/714)
Status: In progress; both materialization application boundaries fixed locally

## Objective

Consolidate position-timeseries generation and portfolio-timeseries aggregation into one
operationally coherent derived-state runtime without combining their domain policies. Remove the
same-owner internal command hop and duplicate deployable overhead while preserving durable queue,
ordering, backdated-restatement, lineage, and downstream data-product contracts.

## Current Finding

The first reviewed stage placed application orchestration inside
`PositionTimeseriesConsumer`. The Kafka adapter opened SQLAlchemy sessions, loaded ORM snapshots,
calculated material state, propagated backdated changes, and staged portfolio aggregation jobs.
Its 366 source lines and 785-line test suite coupled transport, application, calculation, and
persistence concerns and made the runtime consolidation harder to perform safely.

The event also repeated portfolio, security, date, and epoch identity beside the persisted snapshot
ID. The prior flow loaded the authoritative snapshot by ID but queried prior state using the repeated
event fields, so an internally inconsistent event could combine identities across portfolios,
securities, dates, or epochs.

The portfolio stage repeated the same coupling: `PortfolioTimeseriesConsumer` owned database
sessions, portfolio and epoch reads, position fan-in, calculation, queue transitions, output
persistence, outbox composition, and failure writes. Its calculation also logged and skipped a
position when instrument reference data was missing, allowing an incomplete portfolio aggregate to
be published as complete.

## Layering Decision

Use the governed dependency direction for position-timeseries materialization:

1. the Kafka adapter validates the source event and maps it to a framework-neutral command;
2. `MaterializePositionTimeseries` coordinates current-day calculation and bounded backdated
   propagation;
3. `PositionTimeseriesLogic` retains calculation policy;
4. a typed repository port carries immutable domain records and durable effects;
5. the SQLAlchemy provider owns the transaction, ORM mapping, and aggregation-job staging.

Validate the repeated trigger identity against the authoritative persisted snapshot before any
write. Valid triggers continue unchanged; inconsistent triggers fail closed and follow the existing
delivery failure/DLQ path.

Apply the same direction to portfolio-timeseries materialization:

1. map the internal aggregation event to `MaterializePortfolioTimeseriesCommand`;
2. coordinate fan-in, calculation, typed queue disposition, output, and completion evidence in
   `MaterializePortfolioTimeseries`;
3. keep calculation behind a typed calculator port and durable effects behind a repository port;
4. compose the repository and completion-event stager through one SQLAlchemy/outbox unit of work;
5. record expected calculation/source failures on the owned queue job and reserve DLQ handling for
   malformed delivery or failure-persistence errors.

Reject missing instrument reference data instead of skipping a position contribution. Normalize
security identity before batched instrument lookup so padded historical identifiers do not create a
false missing-reference failure.

## Layering Scorecard

| Measure | Before | After |
| --- | ---: | ---: |
| Kafka consumer source lines | 366 | 109 |
| Consumer-owned SQLAlchemy/session concerns | yes | no |
| Consumer-owned calculation/propagation concerns | yes | no |
| Framework-neutral application command/result | no | yes |
| Typed position-timeseries repository/provider ports | no | yes |
| Trigger-to-snapshot identity validation | no | yes |
| Timeseries-generator unit tests | 42 | 42 |
| Portfolio aggregation consumer source lines | 209 | 81 |
| Portfolio consumer-owned SQL/outbox/calculation concerns | yes | no |
| Typed portfolio command/result/repository/calculator/UoW ports | no | yes |
| Missing-instrument portfolio behavior | silently skip position | fail closed |
| Portfolio-aggregation unit tests | 50 | 62 |

The test count is stable because database-heavy consumer scenarios moved to application and
infrastructure suites instead of being deleted or replaced with superficial coverage.

## Correctness And Performance

- Current-day materialization remains idempotent on the complete persisted business state.
- Missing snapshots remain no-ops rather than creating speculative rows.
- Backdated propagation recalculates beginning market value through bounded batches.
- Propagation stops when state converges or a future timeseries row is absent.
- Exact-cap work does not report false truncation; overflow is explicitly reported.
- Aggregation dates are sorted and deduplicated before one bulk upsert.
- Completed aggregation jobs are rearmed; in-flight jobs retain ownership and request reprocessing.
- Correlation diagnostics remain durable when source lineage is missing.
- One command runs in one SQLAlchemy transaction.
- Queue completion/requeue/lost-ownership transitions are typed repository outcomes.
- Portfolio output and completion/reconciliation events share one transaction.
- Missing or invalid FX and missing instrument reference data cannot publish partial aggregates.

## Compatibility

No Kafka topic, event schema, database table, queue identity, calculation field, query/QCP API,
OpenAPI schema, image, health endpoint, metric, or downstream response changed in this slice.

Intentional fail-closed changes apply to:

1. a malformed position trigger whose repeated identity disagrees with its persisted snapshot;
2. a portfolio position whose authoritative instrument reference data is absent.

Both cases now fail before derived output instead of risking mixed-identity or understated state.

## Validation

- `42 passed` across the complete timeseries-generator unit suite.
- Full configured MyPy passed across `235` source files.
- Service-wide Ruff lint and format checks passed.
- Architecture, domain-layer, testability, mapping, runtime-provider, application-layer,
  application-port, dependency-inversion, command/result, infrastructure-adapter,
  repository-transaction, and repository-port guards passed.
- `git diff --check` passed.
- Signed commit `109d69f0c` contains the implementation and tests.
- `62 passed` across the complete portfolio-aggregation unit suite.
- Signed commits `c91711af6`, `d313c79e8`, and `434b3dcf9` own queue transitions, application
  extraction, and missing-instrument correctness respectively.

## Same-Pattern Review

Both delivery paths are now thin and application-owned. The remaining same-pattern work is the
legacy `core` placement and mixed market-data orchestration inside portfolio calculation, followed
by the internal scheduler-to-Kafka-to-consumer command hop. It remains tracked by #714; no duplicate
issue is required. The aggregation scheduler's typed provider, repository, clock, metric, and
publication boundaries must not be flattened during consolidation.

## Documentation Decision

Repository context, this architecture ledger, and the timeseries developer/operator guides change
because dependency and failure-handling truth changed. README, wiki, API inventory, OpenAPI,
supported-features, and migration material remain unchanged because deployable topology and public
contracts are still unchanged. Runtime-facing surfaces must change atomically with the later cutover.

## Remaining Work

1. Move portfolio aggregation calculation and source-enrichment responsibilities out of the legacy
   `core` folder while keeping pure arithmetic separate from market-data access.
2. Replace the same-owner Kafka aggregation command with bounded durable database workers using
   `FOR UPDATE SKIP LOCKED` and stale-claim recovery.
3. Compose one `portfolio_derived_state_service` runtime with independently configurable stage
   concurrency and attributable metrics.
4. Retire the obsolete image, package, health/runtime manager, topic/group, configuration, and
   deployment inventory only after usage and rollback proof.
5. Run daily, burst, backdated, fan-in, duplicate, poison, restart, stale-recovery, concurrency,
   reconciliation, load, release, and exact-main validation before closing #714.
