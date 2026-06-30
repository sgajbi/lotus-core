# CR-1196: Ingestion Rate-Limit Scope Contract

Date: 2026-06-30

## Objective

Address GitHub issue #684 by making ingestion write rate-limit enforcement scope explicit and
startup-validated. Operators must not misread the default in-process limiter as a global scaled
service-level abuse-protection control.

## Change

- Added `LOTUS_CORE_INGEST_RATE_LIMIT_ENFORCEMENT_SCOPE` with supported values:
  `local_process`, `upstream_gateway`, and `local_process_with_upstream_gateway`.
- Added `LOTUS_CORE_INGEST_RATE_LIMIT_GATEWAY_POLICY_ID` and a startup contract validator that
  fails gateway-backed scopes when no gateway policy identifier is configured.
- Added `ingestion_write_rate_limit_contract()` so the service can log whether global enforcement
  is claimed, whether the local process limiter is active, and which policy scope is configured.
- Kept the existing local rolling-window limiter as the default compatibility path.
- Added local denial observability through `ingestion_write_rate_limit_denials_total` with bounded
  `endpoint`, `reason`, and `enforcement_scope` labels plus source-safe warning logs.
- Documented that `local_process` is not a global control across workers, containers, or pods.

## Expected Improvement

The ingestion write plane now has an explicit abuse-protection control boundary. Local enforcement
remains useful for development and defense in depth, while scaled deployments must either select a
gateway-backed scope with a declared policy ID or avoid claiming global rate-limit enforcement. This
prevents a bank-buyability control from being overstated and creates a reusable pattern for future
abuse-protection features: declare enforcement scope, validate production claims, and emit bounded
operator evidence.

## Tests Added

- Settings tests prove default `local_process` scope, gateway policy loading, and invalid-scope
  fallback.
- Ops-control tests prove the local scope does not claim global enforcement.
- Ops-control tests prove gateway-backed scopes require a policy ID and report the policy in the
  contract.
- Ops-control tests prove upstream-gateway-only scope bypasses the local in-process deque.
- Ops-control tests prove local denials include reason-specific errors and bounded metric labels.

## Validation Evidence

- `python -m pytest tests/unit/services/ingestion_service/test_ops_controls.py tests/unit/services/ingestion_service/test_settings.py -q`
  passed with 17 tests.
- `python -m ruff check src/services/ingestion_service/app/ops_controls.py src/services/ingestion_service/app/settings.py src/services/ingestion_service/app/main.py tests/unit/services/ingestion_service/test_ops_controls.py tests/unit/services/ingestion_service/test_settings.py`
  passed.
- `python -m ruff format --check src/services/ingestion_service/app/ops_controls.py src/services/ingestion_service/app/settings.py src/services/ingestion_service/app/main.py tests/unit/services/ingestion_service/test_ops_controls.py tests/unit/services/ingestion_service/test_settings.py`
  passed.

## Downstream Compatibility

Existing route paths, request DTOs, response DTOs, HTTP status mapping, default enabled state,
window size, request budget, record budget, endpoint scoping, and local denial behavior are
preserved by default.

The intentional behavior change is startup validation for gateway-backed scopes: selecting
`upstream_gateway` or `local_process_with_upstream_gateway` now requires
`LOTUS_CORE_INGEST_RATE_LIMIT_GATEWAY_POLICY_ID`. Local denials also include an explicit reason and
enforcement scope in the error message and observability evidence.

## Documentation

- Updated `docs/operations/ingestion-api-gold-standard.md`.
- Updated the codebase review ledger.
- Updated the quality scorecard and refactor health report.
- No wiki update required because repo-local wiki does not currently carry ingestion rate-limit
  operator truth.

## Follow-Up

Issue #684 remains open for PR/CI/QA evidence and platform-ingress validation of the concrete
gateway policy. A future shared-store token-bucket adapter, such as Redis-backed enforcement, can be
added as a separate slice if Lotus chooses service-owned global enforcement instead of gateway-owned
global enforcement.
