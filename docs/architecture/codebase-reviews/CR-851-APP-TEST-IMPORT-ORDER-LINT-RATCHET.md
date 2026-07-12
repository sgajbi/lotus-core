# CR-851: App And Test Import Order Lint Ratchet

Status: Hardened on 2026-06-02.

## Finding

After the governance-helper import-order cleanup, the Ruff baseline still carried 20 import-order
findings across ingestion app modules, query-service app modules, query-control-plane enterprise
readiness, and focused test modules.

## Change

Ran Ruff import organization against the exact remaining app and test files reported by the
`I001` baseline. This removes the last import-order findings without changing executable code,
route registration, DTO definitions, test assertions, or runtime behavior.

Full Ruff findings are down from 271 to 251 after this slice. The `I001` subset is now clean.

## Boundary Preserved

This change does not alter:

1. API routes or router registration semantics,
2. DTO fields or examples,
3. enterprise-readiness middleware behavior,
4. ingestion service publish behavior,
5. repository or database behavior,
6. test assertions.

## Wiki Decision

No repo-local `wiki/` source update is included. This is import-order normalization and quality
evidence maintenance with no operator-facing behavior change.

## Validation

Local validation passed for the slice:

1. `python -m ruff check . --select I001 --statistics`,
2. `python -m ruff check . --statistics`,
3. focused unit tests for touched helper/guard/doc modules,
4. collection checks for touched integration modules,
5. direct import checks for touched app modules,
6. git diff whitespace checks.
