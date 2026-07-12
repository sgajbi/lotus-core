# CR-1110: Ingestion Retry Permission Boundary

Date: 2026-06-20

## Scope

Move ingestion retry permission orchestration out of `ingestion_job_service.py` without changing
retry/replay guardrail semantics, ops-mode behavior, backlog counting scope, public service method
signatures, or reprocessing publish checks.

## Finding

`IngestionJobService` still owned backlog counting, replay record-count permission checks,
ops-mode window wiring, and reprocessing publish permission normalization inline. The code was
already low-complexity, but it kept retry safety policy wiring inside the public service facade and
left a now-unused error-budget default wrapper behind after previous helper extractions.

## Action

Added `ingestion_retry_permissions.py` for:

- backlog job counting
- retry permission orchestration around `assert_replay_guardrails`
- reprocessing publish record-count normalization

`IngestionJobService` keeps the same public methods and still passes `self.get_ops_mode` plus
`self._count_backlog_jobs` into the helper, preserving the current patchable service-test seam and
public behavior. Removed the obsolete `_default_error_budget_status` wrapper.

## Result

`ingestion_job_service.py` improved from `A (41.09)` / 550 SLOC to `A (44.24)` / 522 SLOC under
Radon. The new retry-permission helper reports `A (68.59)` / 50 SLOC. All service and helper
functions remain A-ranked by cyclomatic complexity.

## Evidence

- `python -m pytest tests/unit/services/ingestion_service/services/test_ingestion_job_service_guardrails.py -q`
  => 18 passed
- `python -m pytest tests/unit/services/ingestion_service/services -q`
  => 79 passed
- `python -m ruff check src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_retry_permissions.py tests/unit/services/ingestion_service/services`
  => all checks passed
- `python -m ruff format --check src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_retry_permissions.py tests/unit/services/ingestion_service/services`
  => 18 files already formatted
- `python -m radon mi -s src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_retry_permissions.py`
  => service `A (44.24)`, helper `A (68.59)`
- `python -m radon raw src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_retry_permissions.py`
  => service 522 SLOC, helper 50 SLOC
- `python -m radon cc -s -a src/services/ingestion_service/app/services/ingestion_job_service.py src/services/ingestion_service/app/services/ingestion_retry_permissions.py`
  => all service/helper functions A-ranked; average complexity `A (1.18)`

## Wiki Decision

No wiki source update is required. This is an internal service-helper extraction that preserves
public API behavior, retry/replay semantics, metric contracts, OpenAPI contracts, and
operator-facing documentation truth.
