# CR-1650 Worktree Python Source Provenance

## Status

Fixed locally on `fix/ci-evidence-stability`; protected Linux CI, PR merge, exact-main validation,
and verified issue #763 closure remain pending.

## Finding and reproduction

From clean exact Core main `4ae17adb4`, ambient Python resolved `portfolio_common` from the separate
`lotus-core-correctness-wt` checkout at `16b2af2ac`. Its editable distribution metadata pointed to
that worktree as well. A transaction capability guard passed because the two registry files happened
to match, demonstrating a possible false pass rather than safe provenance. Prepending the invoking
checkout's repository and shared-library roots made the same import resolve current source.

CR-1636 pins quality-tool versions and runs those tools with the active interpreter. It does not
control which checkout supplies first-party Python packages, so #763 remained valid.

## Bounded implementation

`scripts/development/repository_python.py` is now the single Make-owned launcher. It:

- prepends the invoking checkout's repository root and `portfolio-common` source root;
- removes inherited `PYTHONPATH` entries that identify another `lotus-core*` checkout while
  retaining unrelated Python paths;
- proves `portfolio_common` resolves under the invoking checkout before delegating;
- reports expected and actual provenance plus `make install` remediation on failure;
- invokes `[sys.executable, *arguments]` with `shell=False`, the current repository as `cwd`, the
  fenced environment, inherited terminal streams, and the child exit code.

Every Python-backed Make recipe now uses `$(REPOSITORY_PYTHON)`. This includes installation,
architecture, lint, typecheck, unit/integration manifests, OpenAPI/vocabulary, migration, recovery,
latency/performance, release, and cleanup commands. The quality-tool pinning layer remains intact
inside the launcher. Bootstrap additionally verifies the installed editable `portfolio-common`
distribution points to the invoking worktree.

## Compatibility and boundaries

No product runtime, API, OpenAPI, event, database schema, migration, container topology, or test
semantics changed. Direct diagnostics remain available through the launcher, while Make targets are
the supported contract. The launcher does not globally add service-local roots because multiple
service distributions expose an `app` package; focused service import diagnostics must add only the
specific service root to `PYTHONPATH` before invoking the launcher.

No repo-local wiki source change is required. Existing wiki onboarding already directs users to
`make install` and does not document ambient Python behavior. The operations runbook and repository
context own the detailed provenance contract.

Cross-repository static candidates remain outside this Core slice. Each repository requires its own
dynamic reproduction before a coordinated issue or fix; no speculative duplicates were created.

## Validation

- 44 warning-strict launcher, bootstrap, pinned-tool, Make/workflow governance tests passed.
- A two-root subprocess regression loaded distinguishable current source despite an inherited
  foreign worktree path and preserved child exit behavior without a shell.
- Windows local proof resolved
  `C:\Users\Sandeep\projects\lotus-core-ci-evidence-wt\src\libs\portfolio-common\portfolio_common\__init__.py`.
- `make quality-workflow-governance-gate`, `make transaction-capability-catalog-guard`, and
  `make api-vocabulary-gate` passed through the launcher.
- The complete strict `make architecture-guard` chain passed through the launcher.
- Strict MyPy passed for all three touched source modules; touched Ruff and diff hygiene passed.

GitHub Actions Linux proof, broad lint/type/test lanes, merge, exact-main validation, and
branch/worktree reconciliation remain delivery gates rather than local claims.
