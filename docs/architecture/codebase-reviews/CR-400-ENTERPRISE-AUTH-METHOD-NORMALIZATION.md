# CR-400: Enterprise Auth Method Normalization

Date: 2026-05-28

## Scope

Shared `portfolio_common.enterprise_readiness.EnterpriseReadinessRuntime` authorization and
capability-rule lookup.

## Finding

Enterprise authorization normalized HTTP methods with `upper()` but did not trim whitespace before
enforcement and capability-rule lookup. Direct runtime callers passing padded method values such as
` get ` could miss the intended read/write method classification or capability rule despite using a
semantically valid method.

## Change

Trimmed methods before uppercase normalization in both `authorize_request(...)` and
`required_capability(...)`. Added direct coverage proving padded lower-case `get` still resolves
the governed source-data capability rule and authorizes when the caller has the required
capability.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio-common/test_enterprise_readiness_shared.py -q`
2. `python -m pytest tests/unit/libs/portfolio-common -q`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/enterprise_readiness.py tests/unit/libs/portfolio-common/test_enterprise_readiness_shared.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an
enterprise authorization and capability-rule reliability slice.
