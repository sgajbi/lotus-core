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
- Changed critical modules must satisfy both the 90% line and 85% branch thresholds.
- Missing current critical-module evidence returns the stable
  `CHANGED_CRITICAL_SOURCE_UNMEASURED` finding.
- Invalid or unavailable Git comparison evidence fails the gate instead of becoming an empty diff.

## Implementation

- Added `scripts/quality/coverage_evidence/changed_source_evidence.py` for NUL-safe Git status
  parsing, path normalization, explicit-file evidence, and source-to-import-target mapping.
- Replaced path-only `git diff --name-only` handling with rename/copy-aware
  `git diff --name-status -z --find-renames --find-copies` evidence.
- Made the test manifest and warning-budget runner accept repeatable coverage source targets.
- Kept aggregate Query Service evidence in `query-service-coverage.json` and broadened
  `coverage.json` only to exact changed-critical modules selected by the contract.
- Promoted the contract's unmeasured critical-file policy from report-only to fail-closed.
- Made repository-path normalization preserve leading-dot directories and reject absolute or
  parent-traversing paths.
- Separated contract-only output from measured coverage output so documentation validation cannot
  overwrite release evidence with empty totals.

## Tests Added

- Git add, modify, delete, rename, copy, similarity, spaces, Windows path, malformed record, and
  merge-base fallback cases.
- Explicit current/absent paths and repository-layout coverage target mapping.
- Delete/rename report lineage, current critical-source selection, stable fail-closed findings,
  distinct aggregate/measured totals, and multi-target manifest/warning forwarding.
- Real subprocess coverage evidence proving a renamed replacement module contributes to both line
  and branch thresholds.
- Contract-only report selection preserves the measured report while honoring explicit output
  overrides.

## Downstream Compatibility

This changes CI and evidence behavior only. No application API, OpenAPI schema, event, database,
calculation, metric, Docker runtime, deployment topology, or downstream response contract changes.

## Documentation And Context

- Updated `README.md`, `REPOSITORY-ENGINEERING-CONTEXT.md`, and repo-authored
  `wiki/Validation-and-CI.md`.
- No central platform context or skill change is required; existing CI-enforcement guidance already
  requires fail-closed, exact-source evidence.
- No workflow-file change is required: the PR and main coverage jobs already use full Git history,
  set the governed changed base, and invoke `make coverage-gate`.
- No OpenAPI, migration, API inventory, or runtime documentation change is required because this
  slice changes repository quality evidence only.

## Validation Evidence

- 52 focused coverage, guard, manifest, and warning-budget tests passed after the fail-closed
  path/Git and branch-threshold hardening.
- Strict MyPy passed for all five affected quality modules.
- Scoped Ruff and `git diff --check` passed for each implementation slice.
- Full `make coverage-gate` passed with 4,509 unit tests, 10 deselected tests, 136 integration-lite
  tests, zero unit warnings, the branch-aware 98% Query Service aggregate display, and separate
  aggregate, measured-source, and passing critical-path report artifacts.
- `make docs-evidence-pack`, `make quality-wiki-docs-gate`, and
  `make architecture-docs-catalog-guard` passed.
