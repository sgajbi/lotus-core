# CR-1135 Ingestion Ops Auth Boundary

Date: 2026-06-21

## Scope

Privileged ingestion operations authentication in
`src/services/ingestion_service/app/ops_controls.py`.

## Finding

`require_ops_token(...)` mixed request header extraction, JWT parsing, HS256 signature validation,
JWT claim validation, token-only policy, JWT-only policy, and token-or-JWT fallback policy in one
C-ranked dependency. This is a security-sensitive boundary used by privileged ingestion operations
routes, so the logic needed clearer review seams without changing fail-closed behavior.

Radon reported:

- `require_ops_token`: `C (14)`

## Action Taken

Extracted focused helpers for:

- canonical auth error construction,
- JWT segment decoding,
- HS256 signature validation,
- JWT header, time-window, issuer, audience, and principal handling,
- bearer-token extraction,
- required bearer JWT evaluation,
- required `X-Lotus-Ops-Token` evaluation.

Added direct unit coverage for token-only success, token-only invalid-token denial, JWT-only bearer
success, and token-or-JWT bearer precedence over token headers.

## Evidence

Focused behavior proof:

- `python -m pytest tests\unit\services\ingestion_service\test_ops_controls.py tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_ops_supports_bearer_jwt -q`
- Result: `5 passed`

Focused static proof:

- `python -m ruff check src\services\ingestion_service\app\ops_controls.py tests\unit\services\ingestion_service\test_ops_controls.py`
- Result: passed

Focused type proof:

- `make typecheck`
- Result: passed

Focused complexity proof:

- `python -m radon cc src\services\ingestion_service\app\ops_controls.py -s`
- Result: `require_ops_token` is `A (4)`.

Focused maintainability proof:

- `python -m radon mi src\services\ingestion_service\app\ops_controls.py -s`
- Result: `A (33.73)`

Measured movement:

- `require_ops_token`: `C (14)` -> `A (4)`

## Residual Risk

This slice does not change API routes, auth configuration names, error codes, JWT algorithm support,
or token/JWT precedence semantics. `enforce_ingestion_write_rate_limit(...)` remains a separate
B-ranked helper and should be handled only as a focused rate-limit slice with direct behavior proof.

## Bank-Buyable Control Movement

This slice improves:

- reviewability of privileged ingestion authentication,
- direct proof for token and JWT authentication modes,
- separation of JWT claim supportability checks from request-mode dispatch.

It does not claim full bank-buyable readiness for `lotus-core`.
