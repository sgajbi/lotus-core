# CR-1636: Pinned Repository Quality Tooling

## Objective

Make local, feature, pull-request, mainline, and report-only Python quality evidence resolve the same
explicit tool versions without depending on an ambient or globally installed package.

## Finding

`make lint` launched `python -m ruff` without verifying that the active interpreter matched
`requirements/ci-tooling.lock.txt`. Quality Baseline jobs separately installed unversioned Ruff,
MyPy, Bandit, Vulture, Deptry, Radon, Xenon, and import-linter packages. The report-only job added
another unpinned Interrogate path. A workstation and CI runner could therefore evaluate one commit
with different formatter, lint, type, dependency, security, dead-code, or complexity behavior.

The same-pattern scan distinguished Python quality executables from runtime libraries and test
frameworks. Pytest and its plugins remain governed by `tests/requirements.txt`; application
dependencies remain governed by the shared runtime lock. The quality-tool contract belongs in the
existing CI tooling lock rather than either of those dependency surfaces.

## Change

- Added one framework-independent tooling contract that parses exact `NAME==VERSION` pins,
  normalizes distribution names, rejects ranges and duplicates, verifies the active interpreter,
  and emits one deterministic repository-bootstrap remediation for missing or mismatched tools.
- Module-backed commands execute as an argument list using the same `sys.executable`. No shell
  string, command-window launch, global executable, or platform-specific quoting path is involved.
- Routed repository-native Ruff, MyPy, Bandit, Vulture, Deptry, Xenon, and report-only Radon,
  Interrogate, and pip-audit commands through the runner. Embedded Radon and import-linter paths
  verify their distribution versions before execution.
- Expanded `requirements/ci-tooling.lock.txt` with exact versions for every discovered Python
  quality tool. The existing bootstrap remains the single installer for local and governed CI use.
- Changed Quality Baseline jobs to install the exact lock and invoke repository-native Make targets
  or the shared runner. The report-only posture is unchanged, but report evidence no longer uses a
  different tool source.
- Added behavior tests for exact-pin parsing, name normalization, range/duplicate rejection,
  installed-version mismatch, missing-tool remediation, Windows and Linux interpreter paths, and
  same-interpreter execution. Workflow tests prevent unpinned installs and bare Make tool paths from
  returning.

## Compatibility

This changes developer and CI tool resolution only. It does not change application runtime
dependencies, Python source semantics, lint/format rules, API/OpenAPI, events, database schema,
images, or supported product behavior. A previously accepted local command now fails intentionally
when its active tool version differs from the CI lock; `python scripts/development/bootstrap_dev.py`
is the deterministic recovery command.

## Validation

- 32 focused tooling and workflow-governance tests passed; the repository-native workflow target
  independently reran its 23 tests successfully.
- Exact-version verification passed for Ruff, MyPy, Bandit, Vulture, Deptry, Radon, Xenon,
  import-linter, Interrogate, and pip-audit.
- Repository-wide pinned Ruff check and format passed across 2,048 files.
- Strict MyPy passed across 235 source files.
- Import-linter kept both contracts across 677 analyzed files and 3,299 dependencies.
- Bandit found no issue across 131,706 lines of source; Vulture passed; Deptry found no dependency
  issue across 963 files; Radon maintainability and Xenon complexity passed.
- The expanded tooling lock completed a constrained pip dry-run successfully against
  `requirements/shared-runtime.lock.txt`.
- `git diff --check` passed. Signed implementation commit: `34efd635e`.

## Documentation Decision

README command guidance, the operations runbook, repository engineering context, this review, and
the review ledger change because repository validation truth changed. No API, product, runtime
operation, supported-feature, or client/operator support truth changed; repo-authored wiki and
OpenAPI remain intentionally unchanged.
