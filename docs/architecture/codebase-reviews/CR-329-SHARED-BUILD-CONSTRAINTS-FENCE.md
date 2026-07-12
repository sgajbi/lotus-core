# CR-329 Shared Build Constraints Fence

## Scope
Repository-level constrained Python install path for `lotus-core` local/CI bootstrap and Docker image builds.

## Finding
Even after dependency convergence, `lotus-core` still lacked one enforced install fence. Package metadata was aligned, but local bootstrap and Docker builds still relied on package declarations alone with no shared constraints artifact to enforce the common runtime stack.

Given the repo's current split service framework versions, a single full lockfile is not yet practical. But the shared runtime dependency set still needed one canonical, enforced install boundary.

## Fix
- Added `constraints/shared-build-constraints.txt`
- Wired `scripts/bootstrap_dev.py` to install editable projects, test requirements, and dev tooling under that constraints file
- Wired service Dockerfiles to copy the shared constraints file and export:
  - `PIP_CONSTRAINT=/app/constraints/shared-build-constraints.txt`
- Updated `tests/requirements.txt` to align `asyncpg` and pin `httpx`

## Evidence
- `docker build -f src/services/query_service/Dockerfile -t lotus-core-query-service-buildcheck .`
- `docker build -f src/services/valuation_orchestrator_service/Dockerfile -t lotus-core-valuation-orchestrator-buildcheck .`

## Follow-up
- Move from shared constrained installs to fuller lock artifacts where feasible.
- Standardize or reduce cross-service framework version divergence so a broader lock model becomes realistic.
