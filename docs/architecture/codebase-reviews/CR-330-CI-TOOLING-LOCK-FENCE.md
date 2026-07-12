# CR-330 CI Tooling Lock Fence

## Scope
Pinned CI/local tooling install layer for `lotus-core`.

## Finding
`make install` still installed `ruff`, `mypy`, `pip-audit`, and typing stubs by floating names. Even after shared runtime constraints were added, the repo still allowed build-tool versions to drift between local bootstrap and CI runs.

## Fix
- Added `requirements/ci-tooling.lock.txt`
- Wired `scripts/bootstrap_dev.py` to install the tooling layer from that lock file under the shared build constraints

## Evidence
- workflow YAML parsed successfully after the bootstrap/install path change
- shared build and compose validations remained green after the tooling lock was introduced

## Follow-up
- A full shared runtime lock is still blocked by deliberate cross-service framework divergence.
- The tooling layer is now pinned; the next locking step is broader runtime convergence where practical.
