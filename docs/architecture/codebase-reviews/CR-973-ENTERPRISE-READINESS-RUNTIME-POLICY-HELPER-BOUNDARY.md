# CR-973: Enterprise Readiness Runtime Policy Helper Boundary

Date: 2026-06-05

## Scope

Split shared enterprise readiness runtime policy checks into focused helper boundaries without
changing public service wrappers, runtime configuration issue names, authorization denial reasons,
feature-flag fallback behavior, capability-rule matching, path-template matching, sensitive-field
redaction, audit emission, or middleware response behavior.

## Finding

`EnterpriseReadinessRuntime.validate_enterprise_runtime_config` and
`EnterpriseReadinessRuntime.authorize_request` concentrated runtime policy validation, authz
enablement, required header checks, service identity checks, capability-rule enforcement, and
capability parsing in C-ranked methods. The same module also had B/C-ranked helper hotspots for
feature-flag lookup, sensitive-value redaction, path-rule matching, capability-rule normalization,
and path-template matching. These are security and governance guardrails, so the complexity made
the policy harder to review and extend safely.

## Action

Added focused helpers for issue collection, secret-rotation validation, authorization enablement,
capability-rule requirements, header normalization, required-header checks, service identity
checks, capability parsing, feature-flag lookup, redaction, capability-rule parsing, capability
rule validity, path-template detection, path segmentation, and path-segment matching.

## Result

`validate_enterprise_runtime_config` improved from `C (14)` to `A (5)`.
`authorize_request` improved from `C (18)` to `A (4)`. The enterprise readiness module now reports
only A-ranked cyclomatic complexity entries, with maintainability at `B (13.22)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_enterprise_readiness_shared.py tests\unit\services\query_service\test_enterprise_readiness.py tests\unit\services\query_control_plane_service\test_control_plane_enterprise_readiness.py -q`
  => 62 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\enterprise_readiness.py tests\unit\libs\portfolio-common\test_enterprise_readiness_shared.py tests\unit\services\query_service\test_enterprise_readiness.py tests\unit\services\query_control_plane_service\test_control_plane_enterprise_readiness.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\enterprise_readiness.py tests\unit\libs\portfolio-common\test_enterprise_readiness_shared.py tests\unit\services\query_service\test_enterprise_readiness.py tests\unit\services\query_control_plane_service\test_control_plane_enterprise_readiness.py`
  => 4 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\enterprise_readiness.py -s`
  => all enterprise readiness functions/classes/methods A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\enterprise_readiness.py -s`
  => `enterprise_readiness.py` `B (13.22)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\enterprise_readiness.py`
  => 382 SLOC / 273 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared-library enterprise readiness policy
refactor that preserves public API contracts, denial semantics, runtime configuration behavior,
audit behavior, and operator-facing documentation truth.
