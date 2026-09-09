# CR-1723: Per-Revision Main Releasability

## Invariant

Every revision landed by a rebase merge receives independent, exact-SHA Main Releasability evidence.
Missing, cancelled-only, pending, unreadable or truncated evidence fails closed; a later dispatch
cannot cancel or erase an earlier revision's result.

## Finding

The prior dispatcher used only `pull_request.merge_commit_sha`. A ten-revision sample on
2026-09-09 found nine intermediate revisions with no verdict-bearing run. A tip-only green run did
not prove rollback or bisect targets.

## Correction

- enumerate the exact ordered `base_sha..merge_sha` range;
- verify count, single-parent contiguity and patch identity against the source PR;
- dispatch one immutable tag per revision and retain the dispatch manifest;
- disable cancellation for Main Releasability while preserving PR-lane cancellation;
- anchor immutable `main-gate-coverage-enforcement-v1` to the fixing PR's exact parent so
  concurrent dispatcher ordering cannot exempt an earlier revision;
- run a scheduled/manual audit through `make main-gate-coverage-audit` and retain its JSON report.

The baseline is prospective control truth, not a claim that historical ungated revisions passed.
Historical failures remain reported; duplicate and non-verdict runs remain visible. No application,
financial, API, schema, deployment-topology or deliberately global reference-data behavior changes.

## Evidence Required For Closure

1. focused unit and real-Git-history dispatcher tests;
2. platform auto-merge/releasability validator acceptance;
3. required exact-head PR checks and resolved review findings;
4. a real multi-commit rebase merge with one terminal run per landed revision;
5. scheduled/manual audit success and retained manifest/report artifacts;
6. exact-main validation, wiki publication/parity and branch cleanup.
