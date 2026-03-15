# CR-327 Service Dockerfile BuildKit Cache Mounts

## Scope
Service Dockerfile build efficiency across the multi-service `lotus-core` stack.

## Finding
`lotus-core` service Dockerfiles already used a broadly similar multi-stage pattern, but every image still re-ran `pip install ...` steps without BuildKit cache mounts. That meant repeated Docker-backed gates were paying unnecessary cold package-download and wheel-build cost across the service fleet.

## Fix
- Added `# syntax=docker/dockerfile:1.7` to service Dockerfiles.
- Added `PIP_DISABLE_PIP_VERSION_CHECK=1` to base image environment blocks.
- Switched service `pip install` steps onto BuildKit cache mounts:
  - `RUN --mount=type=cache,target=/root/.cache/pip ...`
- Applied the change across the service image fleet instead of only one or two representative images so the Docker-backed heavy gates benefit consistently.

## Build Evidence
- `docker build -f src/services/query_service/Dockerfile -t lotus-core-query-service-buildcheck .`
- `docker build -f src/services/valuation_orchestrator_service/Dockerfile -t lotus-core-valuation-orchestrator-buildcheck .`

## Important Follow-up
The validated builds surfaced a deeper platform build-risk:
- several services install package versions that downgrade or override `portfolio-common` dependency pins inside the same image

That is not introduced by this slice, but it is now explicit build evidence of dependency-governance drift and should be treated as the next serious build-hardening target.
