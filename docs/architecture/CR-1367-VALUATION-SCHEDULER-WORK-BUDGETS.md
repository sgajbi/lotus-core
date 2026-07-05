# CR-1367 Valuation Scheduler Work Budgets

## Objective

Fix GitHub issue #578 by bounding valuation scheduler poll and dispatch work with explicit runtime
budgets, producer back-pressure handling, recovery-safe carry-forward behavior, and low-cardinality
operator telemetry.

## Changes

- Added `VALUATION_SCHEDULER_POLL_BUDGET_SECONDS`.
- Added `VALUATION_SCHEDULER_DISPATCH_BUDGET_SECONDS`.
- Added valuation scheduler metrics:
  - `valuation_scheduler_poll_duration_seconds`
  - `valuation_scheduler_jobs_claimed_total`
  - `valuation_scheduler_jobs_dispatched_total`
  - `valuation_scheduler_budget_exhausted_total`
  - `valuation_scheduler_producer_backpressure_total`
- Preserved the existing claim and dispatch recovery path so claimed-but-undispatched jobs are
  recovered through `recover_dispatch_failed_jobs(...)`.
- Added a typed `ValuationJobPublishError` so scheduler orchestration can distinguish Kafka
  producer back-pressure from generic publish failures without parsing error strings.
- Updated repo context and the operations runbook.

## Expected Improvement

- Prevents large backfills or slow Kafka delivery from letting one scheduler poll grow without an
  explicit duration budget.
- Keeps remaining valuation work claimable in later polls instead of hiding it behind long-running
  scheduler loops.
- Preserves downstream Kafka topic, event payload, key, header, and durable job-state semantics.
- Gives operators direct poll-duration, claimed, dispatched, budget-exhausted, and producer
  back-pressure signals for support triage.

## Tests Added

- Runtime settings expose poll and dispatch budgets with strict-validation-aware parsing.
- Scheduler reads the new budget environment variables.
- Claim loop stops before the next round when the poll budget is exhausted.
- Dispatch budget exhaustion confirms already queued work and recovers the remaining claimed jobs.
- Kafka producer queue saturation increments scheduler back-pressure telemetry and recovers the
  claimed jobs.

## Validation Evidence

```powershell
python -m pytest tests\unit\libs\portfolio-common\test_valuation_runtime_settings.py tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py tests\unit\libs\portfolio-common\test_event_publisher.py -q
python -m ruff check src\libs\portfolio-common\portfolio_common\valuation_runtime_settings.py src\libs\portfolio-common\portfolio_common\scheduler_dispatch_recovery.py src\libs\portfolio-common\portfolio_common\monitoring.py src\services\valuation_orchestrator_service\app\core\valuation_job_publisher.py src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py tests\unit\libs\portfolio-common\test_valuation_runtime_settings.py tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py
python -m ruff format --check src\libs\portfolio-common\portfolio_common\valuation_runtime_settings.py src\libs\portfolio-common\portfolio_common\scheduler_dispatch_recovery.py src\libs\portfolio-common\portfolio_common\monitoring.py src\services\valuation_orchestrator_service\app\core\valuation_job_publisher.py src\services\valuation_orchestrator_service\app\core\valuation_scheduler.py tests\unit\libs\portfolio-common\test_valuation_runtime_settings.py tests\unit\services\valuation_orchestrator_service\core\test_valuation_scheduler.py
make metric-vocabulary-guard
make architecture-guard
make api-vocabulary-gate
make quality-wiki-docs-gate
git diff --check
```

The generated API route catalog refresh required by `make api-vocabulary-gate` was isolated in a
separate evidence commit because it backfilled stale upload-preview 429 route truth from the prior
upload-budget slice rather than changing the valuation scheduler API surface.

## Downstream Compatibility Impact

No API route, DTO, OpenAPI schema, database schema, Kafka topic, event payload, event header, event
key, consumer group, or runtime topology changed.

Intentional behavior change: valuation scheduler polls now stop dispatching when the poll or
dispatch budget is exhausted. Already queued work is confirmed before returning, and remaining
claimed jobs are recovered through the existing retry/failure policy so later polls can carry work
forward safely.

## Same-Pattern Scan

The adjacent aggregation scheduler has a similar dispatch family but is already tracked separately
through the aggregation scheduler boundary and recovery backlog. This slice does not mix the
aggregation refactor into #578. Future scheduler work should apply the same budget/back-pressure
shape before increasing batch size or dispatch rounds.

## Docs, Context, And Skill Decision

- Repo context updated with the scheduler work-budget rule.
- Operations runbook updated with the budget settings and metric names.
- No wiki source update is required because no separate operator workflow page changed.
- No platform skill update is required in this slice; the durable lesson is repository-specific and
  now lives in repo context plus this review entry.

## Remaining Hotspots

Aggregation and other durable queue schedulers should receive equivalent poll/dispatch budget
controls in their own issue slices if their acceptance criteria require throughput hardening beyond
existing batch limits and dispatch recovery.
