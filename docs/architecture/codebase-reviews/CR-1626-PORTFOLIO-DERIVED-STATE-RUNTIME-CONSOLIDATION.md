# CR-1626: Portfolio Derived-State Runtime Consolidation

Date: 2026-07-15
Issue: [#714](https://github.com/sgajbi/lotus-core/issues/714)
Status: In progress; direct leased aggregation runtime fixed locally, deployable consolidation pending

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

The extracted application path still delegated to a legacy `app/core/portfolio_timeseries_logic.py`
module that mixed asynchronous instrument/FX reads, normalization, caching, logging, and portfolio
arithmetic. The source tree also retained an empty `app/repositories` compatibility package after
repository ownership had moved to infrastructure.

The scheduler then claimed durable rows, published a same-owner Kafka command, and relied on a
consumer in the same deployable to invoke materialization. That duplicated the database queue,
required a private topic, partition tuning, publish recovery, consumer groups, and DLQ handling,
and still lacked token-fenced ownership after stale recovery.

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
3. keep source enrichment behind the typed calculation port, pure portfolio arithmetic under
   `app/domain/portfolio_timeseries`, and durable effects behind a repository port;
4. compose the repository and completion-event stager through one SQLAlchemy/outbox unit of work;
5. record expected calculation/source failures on the owned queue job and reserve DLQ handling for
   malformed delivery or failure-persistence errors.

Reject missing instrument reference data instead of skipping a position contribution. Normalize
security identity before batched instrument lookup so padded historical identifiers do not create a
false missing-reference failure.

Resolve and cache instrument/FX inputs in `CalculatePortfolioTimeseries`, then pass immutable
portfolio-currency contributions to the pure `calculate_portfolio_timeseries` domain function.
Reject blank portfolio or instrument currencies, blank portfolio identity, cross-portfolio rows,
future-dated or future-epoch rows, duplicate normalized security rows, and non-positive FX rates
before derived output. Accept prior-date and prior-epoch rows selected by the repository's
latest-state-at-or-before target-window query; those rows are authoritative carry-forward state,
not cross-window contamination. Do not restore the mixed `app/core` module or the empty repository
compatibility package.

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
| Market-data I/O mixed with portfolio arithmetic | yes | no |
| Framework-free portfolio arithmetic | no | yes |
| Portfolio/window/duplicate-security contribution validation | no | yes |
| Obsolete portfolio calculation/repository paths | 2 | 0 |
| Portfolio-aggregation unit tests | 50 | 75 |
| Same-owner aggregation command topics | 1 | 0 |
| Aggregation transport/runtime source lines removed | 0 | 576 |
| Claimed-job worker concurrency | Kafka partition/consumer pool | bounded application workers |
| Terminal ownership predicate | portfolio/date/status | job id + lease token + status |

The generator test count stayed stable because database-heavy consumer scenarios moved to
application and infrastructure owners instead of being deleted. The aggregation count increased
as source resolution and pure contribution invariants gained separate focused coverage.

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
- Missing portfolio/instrument currency cannot be mistaken for a valid same-currency pair.
- Portfolio arithmetic rejects mixed portfolios, future-date or future-epoch input, and duplicate
  security rows while preserving authoritative prior-state carry-forward.
- Instrument reads remain batched and positive FX rates remain cached by currency pair and date.

## Compatibility

No Kafka topic, event schema, database table, queue identity, calculation field, query/QCP API,
OpenAPI schema, image, health endpoint, metric, or downstream response changed in this slice.

Intentional fail-closed changes apply to:

1. a malformed position trigger whose repeated identity disagrees with its persisted snapshot;
2. a portfolio position whose authoritative instrument reference data is absent;
3. portfolio aggregation with missing currency identity, mixed portfolios, future-date/future-epoch
   contributions, duplicate normalized security contributions, or non-positive FX.

These cases now fail before derived output instead of risking mixed-identity, understated, or
cross-window state.

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
- `73 passed` across the complete portfolio-aggregation unit package after separating enrichment
  from arithmetic.
- Signed commit `7c3fa9393` contains the application/domain split, source and contribution
  invariants, retired-path guard, test redistribution, and empty package removal.
- Signed commit `3165bd41a` aligns the pure contribution guard with the repository's
  latest-state-at-or-before semantics: authoritative prior state carries forward and future state
  fails closed.
- `74 passed` across the complete portfolio-aggregation unit package after the carry-forward
  correction.
- Signed commit `1ab0fe400` adds validated lease identity, leased `SKIP LOCKED` claims,
  token-matched terminal writes, expiry-based requeue/failure, and stale-worker ownership-loss
  proof without activating the path prematurely.
- `86 passed` across the complete portfolio-aggregation unit package after the additive lease
  repository slice.
- Signed commit `b5bbff5ba` activates direct bounded workers, token-fenced materialization,
  expiry-based recovery, runtime-owned lease settings, migrated PostgreSQL proof, and no-return
  guards while deleting the private publisher, consumer, scheduler, and consumer manager.
- `80 passed` across aggregation, package-ownership, scheduler-guard, and local-stack unit proof;
  the replacement PostgreSQL integration test collects successfully. Local DB execution remains
  deferred to CI because Docker Desktop is unavailable.
- Signed commit `712e65781` removes the retired request event/topic from shared configuration,
  supportability inventory, Kafka provisioning, compose settings, and contract tests.
- `102 passed` across the focused aggregation, ownership, event-supportability, scheduler-guard,
  and local-stack closure suite after event-contract retirement.
- The complete architecture gate and configured MyPy over `235` source files passed after the
  calculation ownership change.
- The repository documentation/wiki gate, application-port catalog guard, and `18` focused
  catalog/front-door/wiki guard tests passed after current handoff and ownership docs were aligned.

## Same-Pattern Review

Both delivery paths are now thin and application-owned. Portfolio market-data enrichment and pure
arithmetic have separate owners, and the retired legacy paths have no-return coverage. The next
same-pattern target is the internal scheduler-to-Kafka-to-consumer command hop. It remains tracked
by #714; no duplicate issue is required. The aggregation scheduler's typed provider, repository,
clock, metric, and publication boundaries must not be flattened during consolidation.

## Documentation Decision

Repository context, this architecture ledger, the current architecture map, the application-port
and database catalogs, and the timeseries API/developer guides change because dependency,
source-failure, handoff, and contribution-invariant truth changed. README, wiki, API route inventory,
OpenAPI, supported-features, and migration material remain explicit no-change decisions because
deployable topology and public/operator contracts are still unchanged. Runtime-facing surfaces
must change atomically with the later cutover. The additive lease-operation slice changes no
runtime-facing surface and therefore requires no additional front-door, API, event, or wiki update.

## Remaining Work

1. Complete observability for lease expiry, reclaim, and lost ownership and evaluate heartbeat
   renewal for work approaching the configured lease duration.
2. Compose one `portfolio_derived_state_service` runtime with independently configurable stage
   concurrency and attributable metrics.
3. Retire the remaining obsolete deployable image/package/deployment inventory only after usage and
   rollback proof; the private aggregation topic/group/runtime paths are already removed.
4. Run daily, burst, backdated, fan-in, duplicate, poison, restart, stale-recovery, concurrency,
   reconciliation, load, release, and exact-main validation before closing #714.
