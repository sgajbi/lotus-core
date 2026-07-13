# CR-1557: Repository-Wide Ruff Enforcement

Date: 2026-07-13
Issue: #745
Status: Fixed locally; PR proof pending

## Objective

Ensure every Python production, test, script, adapter, and newly introduced package is covered by
the same repository-native lint and format contract used in Feature, PR, and main CI lanes.

## Finding

`make lint` contained 62 lines of hand-maintained Ruff invocations over selected paths. The list did
not include the transaction-processing package, so the #719 cashflow extraction exposed formatting
drift only when its changed files were checked directly. The repository was already globally clean
and already owned `quality-ruff-gate` and `quality-ruff-format-gate`; the curated list was redundant
as well as incomplete.

## Implementation

- Made `lint` depend on the existing repository-wide Ruff check and format targets.
- Retained every domain, architecture, API, security, test, event, and documentation guard that
  already followed the Ruff commands.
- Added a Make contract test that prevents regression to a selected path list.
- Added subprocess-backed tests proving added, renamed, deleted, and space-containing paths remain
  covered by repository-wide check and format behavior on supported platforms.
- Marked RFC-073's global-gate tightening slice complete and updated README, repository context, and
  wiki source with the canonical command and scope.
- Aligned the RFC index and machine-readable ledger and extended the ledger guard so indexed RFC
  status cannot diverge from any ledger entry for the same RFC.

## Measurable Improvement

- Ruff command maintenance in `lint`: 62 lines to one dependency declaration.
- Python scope checked locally and in governed CI: selected paths to all 1,793 current Python files.
- New Python package onboarding: no Makefile edit required.
- Existing domain-specific guard count and behavior: unchanged.

## Compatibility Decision

No application behavior, API/OpenAPI contract, event contract, database schema, image, deployment,
calculation, downstream response, or runtime topology changed. The `make lint` command remains the
stable caller contract; only its enforcement coverage is strengthened.

Central platform context and skills do not change because repository-wide lint is a local Core
implementation of the existing platform quality contract. Repository context, README, RFC status,
and wiki validation guidance changed because local command truth changed.

## Validation

- `python -m ruff check . --statistics`: passed.
- `python -m ruff format --check .`: 1,793 files already formatted.
- Focused CI-governance and repository-wide path tests: 23 passed.
- RFC index/ledger alignment guard tests: 7 passed.
- `make lint`: passed the complete Ruff and governed contract-guard chain.
- `make quality-wiki-docs-gate`: passed all wiki, front-door, architecture catalog, RFC status,
  supported-feature, and incident-playbook checks.
- `make ci-local`: passed 4,343 unit, 10 database, and 135 integration-lite tests with zero
  warnings, 97.79% aggregate coverage, and 91.24% branch coverage.
- `git diff --check`: passed.

PR CI and post-merge exact-main proof remain required before issue closure.
