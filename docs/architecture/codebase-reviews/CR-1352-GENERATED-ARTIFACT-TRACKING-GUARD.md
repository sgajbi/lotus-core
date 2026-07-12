# CR-1352 Generated Artifact Tracking Guard

Date: 2026-07-05

Related issue: `sgajbi/lotus-core#649`

## Objective

Keep generated build, cache, package, coverage, and evidence artifacts out of authored repository
source truth.

## Expected Improvement

- Fails lint if `src/services/query_service/build/lib` or other disposable generated paths become
  tracked by Git.
- Complements `make clean`: cleanup removes ignored local artifacts, while this guard prevents
  generated artifacts from becoming reviewable source.
- Keeps architecture, security, and source-contract scans focused on authored implementation files.

## Implementation

- Added `scripts/generated_artifact_tracking_guard.py`.
- Added `make generated-artifact-tracking-guard`.
- Wired the guard and focused tests into `make lint`.
- Updated README, Validation/CI wiki source, and repository engineering context.

## Tests Added

- `tests/unit/scripts/test_generated_artifact_tracking_guard.py`
  - flags `src/services/query_service/build/lib`,
  - flags cache/output/package artifact paths,
  - allows authored source, scripts, and architecture docs,
  - normalizes Windows-style tracked paths.

## Downstream Compatibility

Validation and repository hygiene only. No API, OpenAPI, DTO, database schema, Kafka contract,
runtime topology, Dockerfile, package import path, or runtime behavior changed.

## Documentation And Context

- Updated `README.md`.
- Updated `wiki/Validation-and-CI.md`.
- Updated `REPOSITORY-ENGINEERING-CONTEXT.md`.

## Validation Evidence

Planned and recorded before commit:

- `python -m pytest tests/unit/scripts/test_generated_artifact_tracking_guard.py -q`
- `python scripts/generated_artifact_tracking_guard.py`
- scoped Ruff lint/format for the guard and tests
- `make generated-artifact-tracking-guard`
- `make quality-wiki-docs-gate`
- `git diff --check`
