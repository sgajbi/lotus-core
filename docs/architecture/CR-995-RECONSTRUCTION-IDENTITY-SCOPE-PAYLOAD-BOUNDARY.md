# CR-995: Reconstruction Identity Scope Payload Boundary

Date: 2026-06-05

## Scope

Split portfolio reconstruction scope validation from canonical snapshot payload construction without
changing deterministic snapshot ID inputs, source-data-product de-duplication, transaction-window
validation, text validation, epoch validation, or hash output shape.

## Finding

`_canonical_scope_payload` mixed required text validation, optional policy validation, epoch
validation, transaction-window pair/order validation, source-data-product validation, and canonical
payload assembly in one B-ranked helper. This made RFC-0083 portfolio reconstruction identity
policy harder to review as source scope metadata evolved.

## Action

Added focused helpers for reconstruction scope validation and transaction-window validation. The
canonical payload helper now delegates validation and remains responsible only for deterministic
payload assembly.

## Result

`_canonical_scope_payload` improved from `B (7)` to `A (1)`. All functions/classes in
`reconstruction_identity.py` now report A-ranked cyclomatic complexity, and the module remains
A-ranked maintainability at `A (44.37)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_reconstruction_identity.py -q`
  => 12 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\reconstruction_identity.py tests\unit\libs\portfolio-common\test_reconstruction_identity.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\reconstruction_identity.py tests\unit\libs\portfolio-common\test_reconstruction_identity.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\reconstruction_identity.py -s`
  => `_canonical_scope_payload` `A (1)` and all functions/classes A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\reconstruction_identity.py -s`
  => `reconstruction_identity.py` `A (44.37)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\reconstruction_identity.py`
  => 68 SLOC / 68 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal deterministic reconstruction identity helper
refactor that preserves source-scope and snapshot ID semantics.
