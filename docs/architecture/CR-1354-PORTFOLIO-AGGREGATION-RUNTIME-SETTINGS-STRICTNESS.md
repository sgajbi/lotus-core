# CR-1354 Portfolio Aggregation Runtime Settings Strictness

## Scope

Continue GitHub issue #600 by migrating portfolio aggregation runtime controls from a local
silent-fallback parser to the shared strict/local runtime settings helper.

## Objective

Make invalid portfolio aggregation worker and scheduler runtime settings fail fast in strict or
non-local profiles while preserving explicit local fallback behavior for development.

## Changes

1. Replaced the local `_env_positive_int(...)` parser in
   `portfolio_aggregation_service.app.settings` with `portfolio_common.runtime_settings.env_int`.
2. Preserved the existing local clamp-to-one behavior through `minimum_fallback=1`.
3. Added tests for:
   - strict production rejection of malformed scheduler batch size;
   - explicit strict-mode rejection of non-positive consumer count;
   - local fallback logging and clamp behavior for invalid poll interval and batch size.

## Behavior And Compatibility

Existing unset defaults, setting names, dataclass fields, scheduler constructor behavior, consumer
manager behavior, and local/development fallback behavior are unchanged.

Intentional behavior change: strict or non-local deployments now fail startup when invalid
portfolio aggregation consumer count, scheduler poll interval, batch size, stale timeout, or max
attempt settings are present.

No API route, OpenAPI schema, database schema, Kafka topic, event payload, metric name, Dockerfile,
or runtime topology changed.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests\unit\services\portfolio_aggregation_service\core\test_aggregation_scheduler.py tests\unit\services\portfolio_aggregation_service\unit\test_portfolio_aggregation_consumer_manager_runtime.py tests\unit\libs\portfolio-common\test_runtime_settings.py -q`
   - Result: `26 passed`.
2. `python -m ruff check src\services\portfolio_aggregation_service\app\settings.py tests\unit\services\portfolio_aggregation_service\core\test_aggregation_scheduler.py`
   - Result: passed.
3. `python -m ruff format --check src\services\portfolio_aggregation_service\app\settings.py tests\unit\services\portfolio_aggregation_service\core\test_aggregation_scheduler.py`
   - Result: passed.

## Documentation, Wiki, Context, And Skill Decision

Updated the codebase review ledger and repo-local engineering context.

No wiki source update is required because this changes startup validation behavior for invalid
environment values, not operator commands, API shape, runtime support workflow, or published
feature truth.

No central Lotus skill change is required. The reusable rule already lives in the issue-loop and
backend-delivery skills: fix same-pattern areas, update repo context, and validate with focused
tests rather than adding prose-only reminders.

## Remaining Work

GitHub issue #600 should remain open until the remaining legacy fallback paths in
`portfolio_common.config` are reviewed and either migrated to `portfolio_common.runtime_settings`
or explicitly documented as local compatibility defaults with tests.
