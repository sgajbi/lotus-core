# CR-971: Source-Data Security Profile Validator Boundary

Date: 2026-06-05

## Scope

Split source-data security profile validation into focused helper boundaries without changing
profile catalog entries, catalog coverage requirements, tenant and entitlement requirements,
operator-only rules, audit mapping, retention mapping, route-family compatibility, PII-field
requirements, or exception messages.

## Finding

`_validate_source_data_security_profiles` mixed duplicate detection, classification allowlists,
tenant and entitlement requirements, operator-only policy, audit policy, retention policy,
catalog route-family compatibility, PII-field validation, and catalog coverage checks in one
D-ranked function. That made a security-critical shared-library guardrail harder to review and
harder to extend safely.

## Action

Added focused private validators for profile-name recording, classification allowlists, scope
requirements, operator access, operator route-family policy, audit mapping, retention mapping,
route-family compatibility, PII-field checks, and catalog coverage. The public
`validate_source_data_security_profiles` and `validate_dpm_planned_source_data_security_profiles`
entry points remain unchanged.

## Result

`_validate_source_data_security_profiles` improved from `D (25)` to `A (4)`. All touched helper
functions now report A-ranked cyclomatic complexity, and `source_data_security.py` remains
A-ranked maintainability at `A (29.23)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_source_data_security.py -q`
  => 23 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\source_data_security.py tests\unit\libs\portfolio-common\test_source_data_security.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\source_data_security.py tests\unit\libs\portfolio-common\test_source_data_security.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\source_data_security.py -s`
  => `_validate_source_data_security_profiles` `A (4)`; all touched helper functions A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\source_data_security.py -s`
  => `source_data_security.py` `A (29.23)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\source_data_security.py`
  => 683 SLOC / 164 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal shared-library security validator refactor
that preserves public API contracts, RFC-0083 source-data security semantics, and operator-facing
documentation truth.
