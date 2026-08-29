# CR-1714: Quality Ratchet Liveness

Date: 2026-08-29

## Scope

Correct the ineffective production maintainability ceiling and add the first blocking module-size
fitness function for issue #462. This slice changes CI and repository governance only; it does not
change application code, APIs, schemas, migrations, events, calculations, or runtime behaviour.

## Finding

`maintainability_gate.py` defaulted to Radon rank C. Radon's maintainability index emits only A, B,
or C, so the production invocation could not reject a real report. Separately, tracked production
source had no size budget: 9 modules exceed 1,500 physical lines, led by
`portfolio_common/database_models.py` at 5,630 lines.

Clean-checkout measurement found 1,144 tracked Python modules under `src/`, including 10 C-ranked
modules and 9 modules above 1,500 lines. Ignored `build/` output is deliberately outside both
inventories so local generated files cannot alter clean-CI truth.

## Decision

1. Make rank B the default maintainability ceiling.
2. Bank each current tracked C module at its exact Radon MI value with an owner, rationale, and
   issue. New debt, worse debt, unbanked improvement, missing files, and stale entries fail.
3. Set a 1,500-line tracked-module budget. Bank each current exception at its exact line count with
   owner, rationale, issue, and expiry. New, grown, shrunken, resolved, missing, or expired entries
   fail until the baseline is ratcheted.
4. Fail both gates on an empty tracked-file scan.
5. Run the module-size command in the existing required
   `Quality Baseline / Maintainability Gate` job, avoiding a gap between workflow execution and
   branch-protection authority.

The checked-in baselines have zero headroom. They are temporary debt inventories, not exemptions
for adding code to hotspots.

## Evidence

- `make quality-maintainability-gate` passes 1,144 tracked modules with 10 reviewed entries.
- `make quality-source-size-gate` passes 1,144 tracked modules with 9 reviewed entries.
- Running the maintainability gate without its baseline returns exit 1 and names all 10 C-ranked
  files and ranks.
- 67 focused pass/fail, changed-baseline, stale-baseline, expiry, path-traversal, tracked-inventory,
  real-scanner, and empty-scan tests pass with 98% branch coverage across both gate modules.
- Static required-check governance passes with 37 manifest-owned checks.

## Remaining Work

Issue #1062 is complete when PR CI and exact-main validation prove the correction. Issue #462 stays
open: it owns the architecture-contract inventory, bounded-context module decomposition, and
eventual removal of every module-size baseline entry.

No wiki change is required because this is repository-internal CI and source-architecture policy,
not product or operator behaviour.
