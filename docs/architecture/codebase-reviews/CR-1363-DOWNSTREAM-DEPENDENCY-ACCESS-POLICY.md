# CR-1363: Downstream Dependency Access Policy

Date: 2026-07-05

## Objective

Fix GitHub issue #581 by replacing hard-coded dependency/admin timeouts with a reusable downstream
access policy contract.

## Findings

`portfolio_common.health` and `portfolio_common.kafka_admin` still embedded fixed Kafka metadata
timeouts. The same pattern would let future live source-data clients add ad hoc timeout, retry,
pagination, batching, cache, or circuit-breaker behavior without a governed policy.

## Actions Taken

1. Added `portfolio_common.downstream_access.DownstreamAccessPolicy`.
2. Added strict-validation-aware `LOTUS_CORE_DOWNSTREAM_*` settings for connection timeout, request
   timeout, retry attempts, retry backoff, max elapsed retry budget, circuit-breaker posture, max
   page size, max batch size, and cache permission.
3. Wired Kafka readiness checks to use the shared request timeout for `AdminClient.list_topics`.
4. Wired Kafka topic verification retry and metadata lookup to use the shared retry/request policy.
5. Added focused unit tests for defaults, overrides, strict invalid timeout rejection, health Kafka
   timeout propagation, and Kafka admin supplied-policy timeout propagation.
6. Updated repo context, operations runbook, and codebase review ledger so future downstream/source
   adapters inherit the shared policy.

## Expected Improvement

Readiness and admin calls remain bounded by configurable budgets, and future source-data clients
have a concrete policy object for timeout, retry, paging, batching, cache, and circuit-breaker
decisions. This reduces hidden runtime coupling and avoids hard-coded downstream behavior.

## Compatibility

Default behavior is intentionally compatible: Kafka metadata request timeout remains 5 seconds,
topic verification keeps 15 attempts with 4 second fixed backoff and a 60 second elapsed budget.
Existing service route paths, health response shapes, Kafka topics, and runtime topology do not
change.

## Validation Evidence

```powershell
python -m pytest tests\unit\libs\portfolio-common\test_downstream_access.py tests\unit\libs\portfolio-common\test_health.py tests\unit\libs\portfolio-common\test_kafka_admin.py -q
python -m ruff check src\libs\portfolio-common\portfolio_common\downstream_access.py src\libs\portfolio-common\portfolio_common\health.py src\libs\portfolio-common\portfolio_common\kafka_admin.py tests\unit\libs\portfolio-common\test_downstream_access.py tests\unit\libs\portfolio-common\test_health.py tests\unit\libs\portfolio-common\test_kafka_admin.py
python -m ruff format --check src\libs\portfolio-common\portfolio_common\downstream_access.py src\libs\portfolio-common\portfolio_common\health.py src\libs\portfolio-common\portfolio_common\kafka_admin.py tests\unit\libs\portfolio-common\test_downstream_access.py tests\unit\libs\portfolio-common\test_health.py tests\unit\libs\portfolio-common\test_kafka_admin.py
make quality-wiki-docs-gate
$env:PYTHONPATH = "src/services/ingestion_service;src/libs/portfolio-common"; python -c "import app.main; print('ingestion app import ok')"
git diff --check
```

Results: 19 focused downstream-policy, health, and Kafka admin tests passed; scoped Ruff check and
format check passed; `make quality-wiki-docs-gate`, ingestion app import proof, and
`git diff --check` passed. `git diff --check` reported expected CRLF normalization warnings only.

## Documentation Decision

Repo-local context, operations runbook, and the codebase review ledger were updated because the
downstream access policy is now the supported pattern for dependency probes, Kafka admin helpers,
and future downstream/source-data clients. No wiki update is required; this is engineering/operator
configuration detail already covered by the runbook and repo context.
