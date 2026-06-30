# CR-1171 Architecture Direct Import Boundaries

## Objective

Begin addressing GitHub issue #462 by expanding executable architecture boundary checks beyond the
two existing import-linter contracts.

## Issue Triage

Issue #462 is valid and in scope. The repository has documented layering rules, but only two
import-linter contracts were mechanically enforced before this slice. Some broader desired
boundaries are not yet clean because several services still use transitional service/DTO sharing and
FastAPI/SQLAlchemy service construction patterns.

## Baseline Risk

Document-only architecture rules are easy to bypass during fast refactoring. In particular,
contract-family routers must not silently bypass source-data/service boundaries by importing
repositories or other service internals directly.

## Change

Extended `scripts/architecture_boundary_guard.py` with AST-based direct-import rules for clean,
deterministic boundaries:

- query-control-plane routers must not import query-service repositories directly,
- query runtime routers must not import query-control-plane internals,
- ingestion routers must not import other service implementations directly.

Kept `.importlinter` unchanged at two contracts because namespace-style service directories without
top-level `__init__.py` are not consistently modeled by import-linter in this repository.

## Expected Improvement

- `make architecture-guard` now protects selected direct service/router import boundaries.
- The new checks are AST-based, so comments and strings do not produce false positives.
- The executable architecture posture moves closer to the documented layering standard without
  adding speculative broad rules that current code cannot yet satisfy.

## Compatibility And Behavior

No product runtime, API route, OpenAPI schema, database schema, data product, or downstream response
contract changed. The change is CI/static-governance only.

## Tests Added

- `test_direct_import_boundary_flags_forbidden_absolute_import`
- `test_direct_import_boundary_ignores_allowed_dto_import`

## Validation

```powershell
make architecture-guard
make quality-import-boundary-gate
python -m pytest tests\unit\scripts\test_architecture_boundary_guard.py -q
python -m ruff check scripts\architecture_boundary_guard.py tests\unit\scripts\test_architecture_boundary_guard.py
python -m ruff format --check scripts\architecture_boundary_guard.py tests\unit\scripts\test_architecture_boundary_guard.py
```

Observed:

- `make architecture-guard` passed
- `make quality-import-boundary-gate` passed with 2 kept import-linter contracts
- focused architecture boundary tests passed with `2` tests
- Ruff lint passed
- Ruff format check passed

## Residual Issue Scope

Issue #462 remains open. Follow-up work should add further import-linter or script-based rules for:

- clean router -> service -> repository boundaries across additional services,
- transport/framework dependencies in pure domain/calculation modules,
- service-to-service import boundaries after transitional DTO/service sharing is moved behind
  canonical contracts,
- explicitly dated exceptions for current transitional violations.

## Documentation Decision

Updated the codebase review ledger, layering standard, architecture rules, quality scorecard, and
refactor health report. No wiki update was needed because the existing wiki already identifies
`make architecture-guard` as the layering and repository-boundary gate, and the command name did not
change.
