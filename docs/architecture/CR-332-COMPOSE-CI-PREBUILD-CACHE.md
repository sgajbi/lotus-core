# CR-332 Compose CI Prebuild Cache

## Scope
Docker-backed CI jobs for `lotus-core`.

## Finding
The smoke, latency, performance, and recovery gates were all rebuilding compose images inside each job with no cross-run Docker cache import/export. BuildKit was enabled, but the heaviest Docker-backed jobs still rebuilt cold on every run.

## Fix
- Added explicit `image:` tags for compose-built services
- Added `scripts/prebuild_ci_images.py` to prebuild compose images into the local Docker engine with reusable local BuildKit cache
- Updated CI jobs to:
  - restore `.buildx-cache`
  - prebuild images
  - run smoke/latency/performance/recovery scripts without `--build`
- Updated the dedicated Docker build job to use the same cached prebuild path for `query_service`

## Evidence
- `docker compose config -q`
- `python scripts/prebuild_ci_images.py --cache-dir .buildx-cache-smoke --services query_service`
- `.github/workflows/ci.yml` parsed successfully

## Follow-up
- Extend the same cache-backed prebuild approach to other Docker-heavy workflows if they keep paying cold-build cost.
