# CR-326 Container Build Baseline Hardening

## Scope
Build context hygiene and Docker-backed CI baseline for `lotus-core`, with reusable standardization artifacts published to `lotus-platform`.

## Finding
`lotus-core` already had multi-stage service Dockerfiles, but the build baseline still had two broad efficiency and governance gaps:

- `.dockerignore` only excluded Python bytecode and build folders, so Docker builds still sent a much larger repository context than necessary.
- Docker-backed CI jobs were not explicitly enabling BuildKit / Compose CLI build acceleration, even though the pipeline repeatedly runs heavy Docker-backed gates.

These were not correctness bugs, but they are real performance and reproducibility gaps for a banking-grade build standard.

## Fix
- Expanded `.dockerignore` to exclude repo metadata, local caches, coverage output, generated task-run artifacts, docs, tests, and other non-build inputs.
- Enabled `DOCKER_BUILDKIT=1` and `COMPOSE_DOCKER_CLI_BUILD=1` at the CI workflow level.
- Added `docker/setup-buildx-action@v3` to Docker-backed workflow jobs so image builds consistently use the modern builder path.
- Published a reusable platform standard and templates in `lotus-platform`:
  - `platform-standards/Container-Build-and-Image-Engineering-Standard.md`
  - `platform-standards/templates/.dockerignore.backend.template`
  - `platform-standards/templates/Dockerfile.python-service.template`

## Follow-up
- Standardize the `lotus-core` service Dockerfiles onto one shared structural pattern instead of allowing service-local drift.
- Move Docker build jobs toward cache import/export once the workflow model is ready for it.
- Add locked dependency artifacts for truly reproducible Python/image builds.

## Evidence
- `.dockerignore`
- `.github/workflows/ci.yml`
- `C:/Users/Sandeep/projects/lotus-platform/platform-standards/Container-Build-and-Image-Engineering-Standard.md`
- `C:/Users/Sandeep/projects/lotus-platform/platform-standards/templates/.dockerignore.backend.template`
- `C:/Users/Sandeep/projects/lotus-platform/platform-standards/templates/Dockerfile.python-service.template`
