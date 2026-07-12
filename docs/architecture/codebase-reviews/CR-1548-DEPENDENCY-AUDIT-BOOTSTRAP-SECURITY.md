# CR-1548: Dependency-Audit Bootstrap Security

Date: 2026-07-12
Status: Fixed locally; merge proof pending

## Objective

Ensure the isolated dependency-health environment audits a governed, non-vulnerable packaging
bootstrap rather than the virtual-environment module's stale bundled default.

## Finding

The dependency-health gate upgraded pip and installed all application, test, and CI dependencies,
but `setuptools 65.5.0` remained from `venv`. Pip-audit reported five findings across three
advisories, including fixes requiring setuptools 78.1.1 or newer.

## Fix

Pinned current setuptools `83.0.0` in `requirements/ci-tooling.lock.txt`. The existing isolated
installation already consumes that lock before `pip check` and `pip-audit`, so no exception or
vulnerability ignore is introduced. Added a focused regression test for the security bootstrap pin.

Application runtime dependencies and published package contracts do not change.

## Validation Evidence

- Dependency-health unit tests: `4 passed`.
- Full isolated dependency consistency: passed.
- Pip-audit: no known vulnerabilities, with no vulnerability ignores.

## Documentation Decision

The CI tooling lock and review ledger are the durable source of truth. README, wiki, repository
context, and platform skills do not change because runtime package ownership and operator behavior
remain unchanged.
