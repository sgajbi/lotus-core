# CR-1210 Common Runtime Settings Strictness

Date: 2026-06-30

## Objective

Continue GitHub issue #600 by migrating common outbox and valuation runtime settings onto the
shared strict/local runtime settings parser without changing existing local fallback semantics.

## Change

- Extended `portfolio_common.runtime_settings.env_int(...)` with an explicit `minimum_fallback`
  option so existing local clamp behavior can be preserved where it is already part of runtime
  semantics.
- Migrated `portfolio_common.outbox_settings` positive and non-negative integer parsing onto the
  shared strict/local parser.
- Migrated `portfolio_common.valuation_runtime_settings` positive integer parsing onto the shared
  strict/local parser while preserving the existing local non-positive clamp to `1`.
- Added service-specific configuration error aliases for outbox and valuation runtime settings.

## Expected Improvement

Common resilience settings for outbox dispatch and valuation/reprocessing scheduling now fail fast
in strict/non-local profiles instead of silently continuing with invalid configuration. Local
developer behavior remains compatible, including outbox safe-default fallback and valuation's
existing minimum clamp behavior.

## Tests Added

- Shared runtime settings minimum fallback preserves local clamp semantics.
- Outbox runtime settings reject invalid non-positive values in strict mode.
- Valuation runtime settings reject invalid non-positive values in strict mode.

## Validation Evidence

- `python -m pytest tests/unit/libs/portfolio-common/test_runtime_settings.py tests/unit/libs/portfolio-common/test_outbox_dispatcher.py tests/unit/libs/portfolio-common/test_valuation_runtime_settings.py -q`
  passed with 18 tests.
- Scoped Ruff lint and format checks passed for the changed common runtime modules and tests.
- `make typecheck` passed with 50 source files checked.
- `make quality-ruff-gate` passed.
- `make quality-ruff-format-gate` passed with 1,238 files already formatted.
- `make quality-complexity-gate` passed.
- `make quality-maintainability-gate` passed.
- `make architecture-guard` passed.
- `make quality-import-boundary-gate` passed with 2 kept contracts.
- `make quality-wiki-docs-gate` passed.
- `git diff --check` passed.

## Downstream Compatibility

Existing function names, dataclass fields, defaults, outbox local fallback behavior, and valuation
local clamp behavior are preserved. The intentional behavior change is limited to strict/non-local
profiles: invalid outbox, valuation scheduler, and reprocessing worker runtime settings now raise
runtime configuration errors. No API, OpenAPI, database schema, Kafka contract, or response shape
changed.

## Documentation And Wiki

Repository context, codebase review ledger, quality scorecard, and refactor health report were
updated. No repo-local wiki page changed because this slice did not add or change an operator
command, endpoint, runbook workflow, or published API contract.

## Remaining Follow-Up

Issue #600 remains open for remaining app-local runtime settings helpers such as portfolio
aggregation service settings, and for deciding whether ingestion's first-slice local strict parser
should be migrated onto `portfolio_common.runtime_settings`.
