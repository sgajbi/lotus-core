# CR-334: Shared Runtime Lock and Constraint Promotion

## Problem
`lotus-core` had a shared build constraints layer, but it still stopped short of one broader compiled runtime lock for the converged multi-service stack. That left the repo with improved dependency convergence but not one reproducible runtime artifact shared by:
- local bootstrap
- service Docker image builds
- build-time evidence generation

## Why It Matters
For banking-grade builds, the runtime dependency set needs to be:
- reproducible
- auditable
- reused consistently across bootstrap, CI, and Docker image construction

Shared constraints were a good intermediate fence, but after web-stack convergence they were no longer the strongest truthful contract available.

## Change
- Added `scripts/update_shared_runtime_lock.py` to:
  - collect the direct runtime dependency union across service `pyproject.toml` files
  - fail if any floating runtime dependency remains
  - compile `requirements/shared-runtime.lock.txt`
- Added generated artifacts:
  - `requirements/shared-runtime.in`
  - `requirements/shared-runtime.lock.txt`
- Updated `scripts/bootstrap_dev.py` to install against the shared runtime lock
- Added `make compile-runtime-lock`
- Switched service Dockerfiles from the old shared constraints artifact to the shared runtime lock
- Pinned remaining floating direct runtime dependencies needed to compile the broader lock truthfully

## Result
`lotus-core` now has one stronger shared runtime artifact that is used by:
- local bootstrap
- representative service image builds
- the next build-evidence path

This materially reduces resolver drift between developer bootstrap, Docker image construction, and CI.
