# CR-1594: Import-Safe Changed Coverage Discovery

## Objective

Keep changed-critical-source coverage deterministic without importing application packages before
pytest collection, while retaining exact-file coverage enforcement.

## Finding

The changed-source coverage helper converted each changed Python file into a dotted module target.
`pytest-cov` resolves dotted targets through `importlib.util.find_spec(...)`, which can execute
parent package initializers before pytest collection. On PR #781, repeated partial imports
registered transaction-processing Prometheus collectors twice and failed collection with duplicate
timeseries errors. After removing that discovery side effect, the gate truthfully exposed an
uncovered transaction-readiness stage repository at `86.44%` group line coverage against the
governed `92%` minimum.

## Change

1. Map governed changed Python files to their nearest source directory for coverage collection.
2. Continue filtering coverage JSON to every exact changed critical file, so directory collection
   does not broaden pass/fail evidence.
3. Deduplicate changed files that share a source directory to reduce coverage target count.
4. Add focused transaction-readiness repository tests for advisory locking, epoch lookup,
   ownership-preserving upsert, collision rejection, domain mapping, and atomic completion claims.

## Measurable Improvement

- Replaced 42 import-triggering changed-file coverage targets with 13 import-safe source-directory
  targets while preserving all 42 exact changed paths in coverage evidence.
- Removed all duplicate Prometheus collector errors from combined-gate collection.
- Raised `stage_repository.py` from `51.52%` statement coverage and `0%` branch coverage to `100%`
  for both measures in the focused proof.
- Added a regression test that proves same-directory changed sources produce one collection target.

## Compatibility

No production code, financial behavior, API, OpenAPI schema, event contract, metric definition,
database structure, image, runtime topology, or downstream contract changed. Coverage thresholds
and exact changed-file enforcement are unchanged.

## Documentation Decision

The codebase-review ledger changed because CI discovery behavior and validation evidence changed.
README, repository context, supported features, database catalog, API inventory, OpenAPI, wiki
source, image metadata, and platform context require no change.

## Validation

1. Changed-source and coverage-gate unit tests passed.
2. Transaction-readiness repository tests passed with `100%` line and branch coverage.
3. Ruff lint and format checks passed for all touched Python files.
4. The complete combined coverage gate passed without pre-collection package imports or duplicate
   metric registration.

## Remaining Work

Keep #749 open for its broader change-aware CI lane selection and runner-efficiency objective. This
slice fixes the exact changed-source discovery defect and strengthens coverage; it does not alter
workflow lane selection.
