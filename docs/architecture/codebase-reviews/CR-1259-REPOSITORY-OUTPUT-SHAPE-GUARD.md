# CR-1259 Repository Output-Shape Guard

Date: 2026-07-01

## Scope

GitHub issue #648 repository output-shape standard, static detection, and recurrence prevention.

## Finding

GitHub issue #648 is valid. Before this slice, `lotus-core` had typed read-record precedents for
`PortfolioTaxLotWindow:v1` and `PerformanceComponentEconomics:v1`, but there was no repository-wide
standard or deterministic guard that would prevent new public repository methods from exposing ORM
rows across application/source-data boundaries.

The current repository still has legacy ORM-returning public repository methods. Treating those as
clean would be inaccurate; the correct control is a transitional exception register that blocks new
drift and becomes smaller as future slices convert repository outputs to explicit records.

## Action Taken

Added `docs/architecture/repository-output-shape-standard.md` to define the required boundary
pattern for:

1. SQLAlchemy ORM rows,
2. raw SQL tuples and SQLAlchemy row mappings,
3. read-model/domain records,
4. source-data product evidence,
5. API/transport DTO exclusions.

Added `scripts/repository_output_shape_guard.py`.

The guard:

1. scans public repository methods under `src/services`,
2. detects return annotations that expose SQLAlchemy ORM classes imported from
   `portfolio_common.database_models`,
3. fails on new unregistered ORM-returning repository methods,
4. fails on stale transitional exceptions after a method is converted,
5. keeps the current method-level transitional exception register in one place.

Added `make repository-output-shape-guard` and wired it into `make lint` so the signal runs in the
fast static lane.

Added focused tests in `tests/unit/scripts/test_repository_output_shape_guard.py` for:

1. current truth passing,
2. rejecting a new unregistered ORM return,
3. rejecting a stale exception,
4. accepting an explicit read-record return.

This is an in-process design-boundary and CI-enforcement improvement only. It does not introduce a
new runtime service.

## Compatibility

No API route, OpenAPI schema, response DTO, Kafka topic, database schema, source-product identity,
repository SQL query, runtime behavior, or downstream contract changed. The guard is additive
static enforcement.

## Evidence

Focused proof:

- `python -m pytest tests\unit\scripts\test_repository_output_shape_guard.py -q --tb=short`
- Result: `4 passed`

Guard proof:

- `make repository-output-shape-guard`
- Result: passed

Static proof:

- scoped Ruff lint passed for the new guard and tests,
- scoped Ruff format check passed for the new guard and tests.

Feature-lane proof:

- `make lint`
- Result: passed; includes `make repository-output-shape-guard`
- `make typecheck`
- Result: passed; `Success: no issues found in 50 source files`
- `make quality-wiki-docs-gate`
- Result: passed
- `git diff --check`
- Result: passed with Windows line-ending warnings only for touched text files

Stranded-truth reconciliation:

- `git fetch origin --prune; git branch -r --no-merged origin/main`
- Result: only `origin/dependabot/github_actions/github-actions-02325a8da5` and
  `origin/dependabot/pip/python-runtime-b808a9fc65`; no unmerged durable governance branch was
  identified for this slice.

## Documentation And Wiki Decision

Updated architecture docs, repository context, quality reports, and the codebase review ledger
because a new repo-native static guard and repository output-shape standard were added. No
repo-local wiki source update was made because no operator-facing workflow, public API contract,
route behavior, or published data-model table shape changed in this slice.

Wiki publication check:

- `..\lotus-platform\automation\Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`
- Result: failed on pre-existing published-wiki drift for `Data-Models.md`,
  `Mesh-Data-Products.md`, `Operations-Runbook.md`, and `Outbox-Events.md`; no new repo-local wiki
  source page changed in CR-1259.

## Issue Posture

This completes the local implementation criteria for #648:

1. repository output-shape standard exists,
2. high-value source-data paths were converted in CR-1257 and CR-1258,
3. tests verify repository adapters and source-data mappers consume explicit records,
4. a static guard identifies public repository methods exposing ORM return annotations,
5. transitional exceptions are registered and will fail when stale.

Keep remaining ORM-returning methods as follow-up conversion backlog. They are now visible and
guarded instead of silently expanding.

## Bank-Buyable Control Movement

This slice improves:

1. infrastructure/application boundary enforcement,
2. agent-quality guardrails against plausible but weak repository code,
3. CI reliability by using a deterministic local static gate,
4. documentation truth about current exceptions,
5. future ownership clarity for repository output conversion slices.
