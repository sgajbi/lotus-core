# CR-1626: Portfolio Derived-State Runtime Consolidation

Date: 2026-07-15
Issue: [#714](https://github.com/sgajbi/lotus-core/issues/714)
Status: In progress; position-timeseries application boundary fixed locally

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

## First-Slice Decision

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

## First-Slice Scorecard

| Measure | Before | After |
| --- | ---: | ---: |
| Kafka consumer source lines | 366 | 109 |
| Consumer-owned SQLAlchemy/session concerns | yes | no |
| Consumer-owned calculation/propagation concerns | yes | no |
| Framework-neutral application command/result | no | yes |
| Typed position-timeseries repository/provider ports | no | yes |
| Trigger-to-snapshot identity validation | no | yes |
| Timeseries-generator unit tests | 42 | 42 |

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

## Compatibility

No Kafka topic, event schema, database table, queue identity, calculation field, query/QCP API,
OpenAPI schema, image, health endpoint, metric, or downstream response changed in this slice.

The intentional behavior change applies only to a malformed internal trigger whose repeated
identity disagrees with its persisted snapshot. Such a trigger now fails closed before durable
effects instead of risking mixed-identity derived state.

## Validation

- `42 passed` across the complete timeseries-generator unit suite.
- Full configured MyPy passed across `235` source files.
- Service-wide Ruff lint and format checks passed.
- Architecture, domain-layer, testability, mapping, runtime-provider, application-layer,
  application-port, dependency-inversion, command/result, infrastructure-adapter,
  repository-transaction, and repository-port guards passed.
- `git diff --check` passed.
- Signed commit `109d69f0c` contains the implementation and tests.

## Same-Pattern Review

The same transport/application/persistence coupling remains in the portfolio-timeseries delivery
path and is the next bounded #714 slice. It is tracked by the same issue and this review record; no
duplicate issue is required. The aggregation scheduler already has typed provider, repository,
clock, metric, and publication ports and must not be flattened during consolidation.

## Documentation Decision

Repository context and this architecture ledger change because dependency ownership changed.
README, wiki, API inventory, OpenAPI, supported-features, migration, and operator runbook remain
unchanged in this first slice because deployable topology and external/operator contracts are still
unchanged. Those surfaces must change atomically with the later runtime cutover.

## Remaining Work

1. Extract the portfolio-timeseries delivery path into application/domain/port/infrastructure
   ownership while preserving fan-in and calculation behavior.
2. Replace the same-owner Kafka aggregation command with bounded durable database workers using
   `FOR UPDATE SKIP LOCKED` and stale-claim recovery.
3. Compose one `portfolio_derived_state_service` runtime with independently configurable stage
   concurrency and attributable metrics.
4. Retire the obsolete image, package, health/runtime manager, topic/group, configuration, and
   deployment inventory only after usage and rollback proof.
5. Run daily, burst, backdated, fan-in, duplicate, poison, restart, stale-recovery, concurrency,
   reconciliation, load, release, and exact-main validation before closing #714.
