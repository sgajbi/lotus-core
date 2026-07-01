# CR-1245 Outbox Retry Budget Telemetry

Date: 2026-07-01

## Objective

Finish the remaining local gaps for GitHub issue #669 by making outbox retry policy and telemetry
explicit enough for operators and future agents to distinguish retry states without inspecting raw
payloads or inferring behavior from logs.

## Finding

CR-1186 added durable `next_attempt_at` scheduling and bounded exponential retry delays, but issue
#669 still had two local gaps:

- operators could see total pending and failed outbox rows, but not the split between retry-eligible
  pending rows and rows waiting for a future retry window,
- retry policy had max attempts and bounded delay, but no explicit elapsed-budget hook.

## Change

- Added `OUTBOX_DISPATCHER_RETRY_MAX_ELAPSED_SECONDS`.
  - Default `0` preserves existing behavior and means elapsed-budget terminalization is disabled.
  - Positive values terminalize retryable failures once the row age exceeds the configured budget.
- Added low-cardinality gauges:
  - `outbox_events_retry_eligible_pending`
  - `outbox_events_retry_waiting_pending`
- Extended the outbox pending gauge read to emit total pending, retry-eligible pending, retry-waiting
  pending, terminal failed, and oldest pending age in one short diagnostic path.
- Preserved success, retryable failure, terminal failure, durable retry scheduling, and leased-claim
  behavior.

## Expected Improvement

- Operators can distinguish backlog waiting on governed retry windows from backlog eligible for
  immediate dispatch.
- Retry budget policy is explicit and configurable without changing default runtime behavior.
- Future outbox or durable-publish loops have a clearer reusable pattern: durable eligibility,
  bounded attempts, optional elapsed budget, and bounded operator metrics.

## Behavior And Compatibility

- Existing API routes, OpenAPI contracts, Kafka topics, event payloads, event headers, producer API,
  and consumer contracts are preserved.
- Default elapsed-budget behavior is disabled, so existing max-attempt retry behavior remains the
  default.
- The intentional additive runtime behavior is:
  - new internal gauges for retry-state visibility,
  - optional terminalization when `OUTBOX_DISPATCHER_RETRY_MAX_ELAPSED_SECONDS` is configured above
    zero.
- No wiki update is required because no operator command or public runbook changed.

## Tests Added Or Extended

- Extended outbox runtime settings unit tests for retry max elapsed default, environment override,
  local fallback, and constructor override.
- Added unit coverage proving the elapsed retry budget classifies a failed event as terminal even
  before max attempts.
- Extended DB-backed gauge coverage to prove total pending, retry-eligible pending, retry-waiting
  pending, failed, and oldest pending age are emitted separately.

## Validation Evidence

- `python -m pytest tests/unit/libs/portfolio-common/test_outbox_dispatcher.py -q --tb=short`
  - Result: `11 passed`.
- `python -m pytest tests/integration/libs/portfolio-common/test_outbox_dispatcher.py tests/integration/libs/portfolio-common/test_outbox_dispatcher_delivery_results.py -q --tb=short`
  - Result with rebuilt local Docker image: `17 passed`.
- `python -m ruff check src/libs/portfolio-common/portfolio_common/outbox_settings.py src/libs/portfolio-common/portfolio_common/monitoring.py src/libs/portfolio-common/portfolio_common/outbox_dispatcher.py tests/unit/libs/portfolio-common/test_outbox_dispatcher.py tests/integration/libs/portfolio-common/test_outbox_dispatcher.py --ignore E501,I001`
  - Result: passed.
- `python -m ruff format --check src/libs/portfolio-common/portfolio_common/outbox_settings.py src/libs/portfolio-common/portfolio_common/monitoring.py src/libs/portfolio-common/portfolio_common/outbox_dispatcher.py tests/unit/libs/portfolio-common/test_outbox_dispatcher.py tests/integration/libs/portfolio-common/test_outbox_dispatcher.py`
  - Result: passed.
- `python -m mypy --config-file mypy.ini src/libs/portfolio-common/portfolio_common/outbox_settings.py src/libs/portfolio-common/portfolio_common/outbox_dispatcher.py`
  - Result: passed.

## Remaining Work

- Keep issue #669 open for PR, CI, and QA evidence.
- If operators need route-level outbox retry state diagnostics beyond metrics, add them through a
  protected QCP support endpoint rather than exposing raw outbox payloads.
