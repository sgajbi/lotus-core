# CR-1250 Metric Vocabulary Guard

Date: 2026-07-01

## Objective

Fix GitHub issue #566 by making metric names, labels, and service-local ownership governed by a
deterministic repository-native guard.

## Change

- Added the shared metric-label contract in `portfolio_common.observability_contracts`.
- Renamed shared HTTP metric label `path` to `endpoint_template`; the emitted value was already a
  FastAPI route template, so this aligns the label name with the actual bounded value.
- Registered existing service-local persistence and cost-calculator metrics with explicit owners.
- Added `scripts/metric_vocabulary_guard.py`, an AST guard that rejects unsafe or unknown metric
  labels, dynamic label definitions, non-snake-case metric names, and unowned service-local metric
  definitions.
- Wired `make metric-vocabulary-guard` into `make lint`, which is consumed by Feature Lane, PR
  Merge Gate, and main releasability workflows.

## Expected Improvement

Future agent or developer changes cannot silently add sensitive, high-cardinality, or unowned
Prometheus labels such as portfolio IDs, account/client/security IDs, trace/request/correlation IDs,
raw paths, payload fields, raw exception text, or stack traces. Service-local metrics must either
move into the shared registry or be explicitly registered with an owning service.

## Tests Added Or Updated

- Added `tests/unit/scripts/test_metric_vocabulary_guard.py` for current-truth, forbidden-label,
  unowned-service-local, and owned-service-local cases.
- Updated shared HTTP bootstrap tests to assert the governed `endpoint_template` metric label.

## Validation Evidence

- `python scripts\metric_vocabulary_guard.py` -> passed.
- `python -m pytest tests\unit\libs\portfolio-common\test_http_app_bootstrap.py tests\unit\scripts\test_metric_vocabulary_guard.py -q --tb=short`
  -> 16 passed.
- `python -m pytest tests\integration\services\query_service\test_main_app.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py -q --tb=short`
  -> 60 passed.
- `make lint` -> passed, including the new `make metric-vocabulary-guard` hook.
- `make typecheck` -> passed; no issues found in 50 source files.
- `make quality-wiki-docs-gate` -> passed.
- `git diff --check` -> passed.
- `powershell -ExecutionPolicy Bypass -File C:\Users\Sandeep\projects\lotus-platform\automation\Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`
  -> expected unpublished wiki drift for changed `Operations-Runbook.md` plus existing
  `Outbox-Events.md`; publication remains post-merge.
- Stranded-truth reconciliation on 2026-07-01 found only active Dependabot branches:
  `origin/dependabot/github_actions/github-actions-02325a8da5` and
  `origin/dependabot/pip/python-runtime-b808a9fc65`. No CR-1250 durable truth was cherry-picked
  from those branches.

## Downstream Compatibility

No route path, response body, health schema, product API, database schema, or Kafka topic changed.
The only runtime-facing contract change is the Prometheus HTTP metric label key from `path` to
`endpoint_template`; this is intentional because raw/free-form path labels are now forbidden.

## Documentation And Wiki Decision

Updated this architecture record, codebase review ledger, observability docs, operations runbook,
repo-local wiki source, repository context, quality scorecard, refactor health report, and the
ingestion SLO alert example because metric-label governance changed. Wiki publication remains
post-merge.
