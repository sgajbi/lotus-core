# CR-1572 Rename-Aware Changed Coverage Evidence

Date: 2026-07-14

Related issue: `sgajbi/lotus-core#766`

## Objective

Make changed critical-path coverage evidence reflect the post-change repository tree and fail
closed when a current critical module is absent from governed coverage data.

## Expected Improvement

- Deleted files no longer appear as current unmeasured source.
- Rename and copy records retain previous path, current path, Git status, and similarity evidence.
- Query Service keeps its established branch-aware 98% aggregate scope.
- Changed critical modules are added to the same governed unit and integration-lite coverage run.
- Missing current critical-module evidence returns the stable
  `CHANGED_CRITICAL_SOURCE_UNMEASURED` finding.

## Implementation

- Added `scripts/quality/coverage_evidence/changed_source_evidence.py` for NUL-safe Git status
  parsing, path normalization, explicit-file evidence, and source-to-import-target mapping.
- Replaced path-only `git diff --name-only` handling with rename/copy-aware
  `git diff --name-status -z --find-renames --find-copies` evidence.
- Made the test manifest and warning-budget runner accept repeatable coverage source targets.
- Kept aggregate Query Service evidence in `query-service-coverage.json` and broadened
  `coverage.json` only to exact changed-critical modules selected by the contract.
- Promoted the contract's unmeasured critical-file policy from report-only to fail-closed.

## Tests Added

- Git add, modify, delete, rename, copy, similarity, spaces, Windows path, malformed record, and
  merge-base fallback cases.
- Explicit current/absent paths and repository-layout coverage target mapping.
- Delete/rename report lineage, current critical-source selection, stable fail-closed findings,
  distinct aggregate/measured totals, and multi-target manifest/warning forwarding.

## Downstream Compatibility

This changes CI and evidence behavior only. No application API, OpenAPI schema, event, database,
calculation, metric, Docker runtime, deployment topology, or downstream response contract changes.

## Documentation And Context

- Updated `README.md`, `REPOSITORY-ENGINEERING-CONTEXT.md`, and repo-authored
  `wiki/Validation-and-CI.md`.
- No central platform context or skill change is required; existing CI-enforcement guidance already
  requires fail-closed, exact-source evidence.

## Validation Evidence

- 43 focused coverage/manifest/warning tests passed before the contract and documentation slice.
- Strict MyPy passed for all five affected quality modules.
- Scoped Ruff and `git diff --check` passed for each implementation slice.
- Full `make coverage-gate`, documentation evidence, wiki, and repository-native CI gates remain
  required before PR readiness.
