# CR-1626: Portfolio Derived-State Runtime Consolidation

Date: 2026-07-15
Issue: [#714](https://github.com/sgajbi/lotus-core/issues/714)
Status: In progress; deployable consolidation fixed locally, load/recovery/release certification pending

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
3. the pure `calculate_position_timeseries` function and immutable records own calculation policy
   under `app/domain/position_timeseries`;
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
| Timeseries-generator unit tests | 42 | 43 |
| Position-timeseries calculation package | legacy `app/core` class | pure domain function |
| Position-timeseries domain tests coupled to ORM models | yes | no |
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
| Derived-state deployables | 2 | 1 |
| Runtime supervisors / health endpoints / outbox dispatchers | 2 / 2 / 2 | 1 / 1 / 1 |
| Internal aggregation command transports | durable DB queue + private Kafka hop | durable DB queue only |
| Health ports | 8085 and 8088 | 8085 |
| Durable valuation-to-position latency evidence | p50 / p95 / max, insert-oriented | p50 / p95 / p99 / max, upsert-aware |
| Durable position-to-portfolio latency evidence | none | one sample per portfolio/date/epoch |
| Missing latency evidence posture | report could remain green | stage sample counts fail closed |

The generator test count initially stayed stable because database-heavy consumer scenarios moved
to application and infrastructure owners instead of being deleted; it now includes an additional
first-position-day domain invariant. The aggregation count increased as source resolution and pure
contribution invariants gained separate focused coverage.

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
- Position-timeseries arithmetic is a framework-independent pure function over immutable domain
  records; the legacy `app/core` package is retired and guarded against restoration.

## Compatibility

External event schemas, queue/table identity, calculation fields, query/QCP APIs, OpenAPI product
schemas, and downstream responses remain compatible. The batch intentionally:

1. added nullable lease owner/token/UTC-expiry fields and supporting queue constraints/indexes;
2. retired the same-owner internal aggregation request topic, producer, and consumer after proving
   there was no external consumer;
3. retained the valuation-snapshot input and aggregation-completion/reconciliation output events.
4. replaced two internal deployable/package/image identities with
   `portfolio_derived_state_service` / `portfolio-derived-state-service`;
5. retained port `8085`, retired port `8088`, and preserved
   `timeseries_generator_group_positions` so live offsets do not reset;
6. replaced two health/metrics targets with one derived-state health/version/metrics surface while
   preserving separate position and aggregation workload attribution.

No database migration is required: `position_timeseries`, `portfolio_timeseries`, and
`portfolio_aggregation_jobs` retain their schemas and ownership semantics.

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
- Signed commit `24e375327` moves position-timeseries models and arithmetic into the named domain
  package, replaces the static `Logic` class with a pure function, decouples domain tests from ORM
  models, and guards the retired `app/core` and flat record paths.
- `43` tests collect in the complete timeseries-generator unit suite; the focused generator plus
  package-ownership run passed `49` tests. Configured MyPy over `235` source files, Ruff,
  architecture, domain-layer, application-dependency, and workflow-policy guards passed.
- The unified target package, runtime, configuration, deployment, release inventory, and no-return
  pack passes `163` focused tests.
- Ruff passes across target source/tests and touched runtime/release scripts; MyPy reports no issues
  across all `46` target service source files.
- Runtime-boundary, application-port, aggregation-scheduler, architecture, image-provenance, API
  route catalog, Compose rendering, and Kubernetes digest/security guards pass.
- The image-release matrix now builds only `portfolio-derived-state-service`, writes digest, SBOM,
  vulnerability, signature, and provenance evidence, and renders its Kubernetes deployment from
  the same digest release manifest used across dev, UAT, and prod.
- `control_queue_operations_total{queue="aggregation"}` exposes bounded lease-recovery, claim,
  complete, requeue, lost-ownership, terminal-failure, and execution-error outcomes through the
  scheduler metrics port and the app-local Grafana dashboard.
- The bank-day load report now records p50, p95, p99, maximum, and sample counts for both durable
  materialization stages. Valuation-to-position samples use matching completed job and position
  identities; position-to-portfolio samples group once per portfolio/date/epoch and start from the
  final updated position input so security count cannot bias fan-in percentiles.
- The focused bank-day, reconciliation-report, and institutional-sign-off tooling suite passes
  `25` tests; scenario MyPy, CI-pinned Ruff `0.15.18`, documentation/wiki gates, and diff checks
  pass. PostgreSQL execution and measured percentiles remain runtime evidence, not source proof.
- Signed commit `dbdd729ed` adds a managed interruption gate that pauses the exact unified
  container, proves source snapshots and committed lag accumulate, then requires exact output
  counts, closed valuation/aggregation queues, baseline lag recovery, zero reconciliation
  findings, and zero added DLQ events. Its focused gate and service-set suite passes `14` tests;
  Ruff, MyPy, and diff checks pass.
- PR and main-releasability workflow wiring is covered by exact-image-set, managed-diagnostics,
  action-version, and service-set contracts. A live PostgreSQL/Kafka execution remains required
  before this source-level gate can count as deployed recovery evidence.

## Same-Pattern Review

Both delivery paths are now thin and application-owned. Position and portfolio arithmetic are pure
domain policies under explicitly named packages, source enrichment is application-owned, and the
retired legacy paths have no-return coverage. The internal scheduler-to-Kafka-to-consumer command
hop, duplicate runtime shells, old packages, old images, and old deployment inventory are removed
and guarded against restoration. Position and portfolio materializers remain separately testable
modules with independently configured aggregation concurrency and attributable metrics inside the
target runtime.

## Documentation Decision

README, repository context, this review, current architecture/runtime/port catalogs, schema usage
catalog, feature docs, operations references, and authored wiki change because deployable and
operator truth changed. The API route catalog is regenerated for one standard health surface.
Public business OpenAPI, event schemas, database migrations, and downstream product contracts are
explicit no-change decisions because this cutover changes internal runtime topology only.

## Remaining Work

1. Run daily, burst, backdated, and fan-in profiles and compare both stage p50/p95/p99/max results
   against the configured lease duration. Use those measured job durations to decide whether fixed
   expiry is sufficient or heartbeat renewal is required.
2. Execute `make test-derived-state-recovery-gate`, retain its machine-readable evidence, and run
   remaining duplicate, poison, stale-lease, concurrency, load, release, and exact-main validation
   before closing #714.
3. Execute controlled offset/deployment rollback proof and canonical cross-repo QA after CI can
   build and run the combined image against PostgreSQL and Kafka.
