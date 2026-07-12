# CR-972: Outbox Dispatcher Batch Orchestration Boundary

Date: 2026-06-05

## Scope

Split shared outbox batch orchestration into focused helper boundaries without changing pending-row
selection, transaction boundaries, Kafka publish inputs, correlation-header propagation, delivery
callback accounting, flush-timeout handling, retry increments, terminal failure behavior, metrics,
or log events.

## Finding

`OutboxDispatcher._process_batch_sync` mixed queue gauge reads, pending-row claiming, delivery
callback creation, payload/header construction, synchronous publish failure handling, producer
flush accounting, delivery classification, retryable failure persistence, terminal failure
persistence, metrics, and logging in one E-ranked method. This is a cross-service operational
reliability path, so the complexity made it harder to review and maintain safely.

## Action

Added focused helpers for event publishing, flush-result accounting, delivery-result
classification, success persistence, retryable failure persistence, terminal failure persistence,
delivery callback creation, event headers, event payloads, and callback-less failure accounting.
The public dispatcher API and `_process_batch_sync` entry point remain unchanged.

## Result

`OutboxDispatcher._process_batch_sync` improved from `E (33)` to `A (2)`. All dispatcher methods
and outbox helper functions now report A-ranked cyclomatic complexity, and `outbox_dispatcher.py`
remains A-ranked maintainability at `A (40.41)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_outbox_dispatcher.py -q`
  => 6 passed
- `python -m pytest tests\unit\libs\portfolio-common\test_outbox_dispatcher.py tests\integration\libs\portfolio-common\test_outbox_dispatcher.py tests\integration\libs\portfolio-common\test_outbox_dispatcher_delivery_results.py -q`
  => 6 unit tests passed; 13 integration tests could not start because local Docker Desktop/daemon
  was unavailable (`docker info` could not connect to `dockerDesktopLinuxEngine`)
- `python -m ruff check src\libs\portfolio-common\portfolio_common\outbox_dispatcher.py tests\unit\libs\portfolio-common\test_outbox_dispatcher.py tests\integration\libs\portfolio-common\test_outbox_dispatcher.py tests\integration\libs\portfolio-common\test_outbox_dispatcher_delivery_results.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\outbox_dispatcher.py tests\unit\libs\portfolio-common\test_outbox_dispatcher.py tests\integration\libs\portfolio-common\test_outbox_dispatcher.py tests\integration\libs\portfolio-common\test_outbox_dispatcher_delivery_results.py`
  => 4 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\outbox_dispatcher.py -s`
  => `_process_batch_sync` `A (2)`; all dispatcher methods and outbox helpers A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\outbox_dispatcher.py -s`
  => `outbox_dispatcher.py` `A (40.41)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\outbox_dispatcher.py`
  => 314 SLOC / 159 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared-library dispatcher refactor that
preserves public API contracts, outbox delivery semantics, observability metrics, and
operator-facing documentation truth.
