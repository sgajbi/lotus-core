# CR-1356 Capability Rule Exact Path Matching

## Scope

Fix GitHub issue #584 in the shared enterprise authorization helper.

## Objective

Prevent a capability rule for a narrower path template from authorizing deeper child routes unless
the rule explicitly declares subtree intent.

## Changes

1. Made capability path matching exact by default for literal and templated routes.
2. Added explicit subtree syntax with `/**`.
3. Preserved intended parent-route authorization in tests by changing those rules to `/**`.
4. Added regression tests for:
   - exact templated route matching;
   - deeper child-route denial for `/{id}` templates;
   - explicit templated subtree allow with `/{id}/**`;
   - specificity ordering with explicit subtree rules.

## Behavior And Compatibility

Intentional security behavior change: a rule such as `GET /portfolios/{portfolio_id}` now matches
only that exact segment shape. To authorize child paths, configure
`GET /portfolios/{portfolio_id}/**`.

Generated source-data capability rules already use concrete route templates and remain exact. No
API route path, OpenAPI schema, database schema, Kafka contract, metric name, Dockerfile, or runtime
topology changed.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests\unit\libs\portfolio-common\test_enterprise_readiness_shared.py tests\unit\services\query_service\test_enterprise_readiness.py tests\unit\services\query_control_plane_service\test_control_plane_enterprise_readiness.py tests\unit\services\query_service\test_query_service_settings.py tests\unit\services\query_control_plane_service\test_control_plane_settings.py -q`
   - Result: `83 passed`.
2. `python -m ruff check src\libs\portfolio-common\portfolio_common\enterprise_readiness.py tests\unit\libs\portfolio-common\test_enterprise_readiness_shared.py tests\unit\services\query_service\test_enterprise_readiness.py tests\unit\services\query_service\test_query_service_settings.py`
   - Result: passed.
3. `python -m ruff format --check src\libs\portfolio-common\portfolio_common\enterprise_readiness.py tests\unit\libs\portfolio-common\test_enterprise_readiness_shared.py tests\unit\services\query_service\test_enterprise_readiness.py tests\unit\services\query_service\test_query_service_settings.py`
   - Result: passed.

## Documentation, Wiki, Context, And Skill Decision

Updated the codebase review ledger and repo-local engineering context.

No wiki source update is required because this is an internal authorization rule-matching contract;
operator-facing auth policy publication remains in existing security and operations pages.

No central Lotus skill change is required. The repeatable lesson is repository-local: capability
rule examples and tests must use exact path templates or explicit `/**` subtree syntax.
