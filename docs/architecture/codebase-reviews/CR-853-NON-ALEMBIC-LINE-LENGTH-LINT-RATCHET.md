# CR-853: Non-Alembic Line Length Lint Ratchet

Status: Hardened on 2026-06-02.

## Finding

After unused-symbol, import-order, and import-position cleanup, Ruff had 250 remaining findings,
all `E501` line-length debt. A small active-code subset lived outside historical Alembic
migrations across scripts, tools, ingestion app modules, query DTOs, cashflow repository code, and
focused tests.

## Change

Reformatted and manually wrapped the bounded non-Alembic subset without changing literal values,
route behavior, DTO field semantics, SQL statements, or test assertions.

Full Ruff findings are down from 250 to 218 after this slice. The remaining findings are still all
`E501`.

## Boundary Preserved

This change does not alter:

1. API routes or DTO fields,
2. ingestion adapter behavior,
3. ops-control authorization behavior,
4. cashflow repository behavior,
5. smoke cleanup SQL semantics,
6. test assertions.

## Wiki Decision

No repo-local `wiki/` source update is included. This is source-formatting and quality-evidence
maintenance with no operator-facing behavior change.

## Validation

Local validation passed for the slice:

1. scoped `python -m ruff check ... --select E501`,
2. `python -m ruff check . --statistics`,
3. focused unit tests for RFC-0083 closure and cashflow repository coverage,
4. direct compilation of touched scripts/app modules,
5. collection check for the touched query-control integration-router test module,
6. git diff whitespace checks.
