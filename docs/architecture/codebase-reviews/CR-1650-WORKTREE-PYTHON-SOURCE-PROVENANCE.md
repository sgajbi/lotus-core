# CR-1650 Worktree Python Source Provenance

## Status

Fixed locally on consolidated branch `fix/demo-pack-content-idempotency`; protected Linux CI, PR
merge, exact-main validation, and verified issue #763 closure remain pending.

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
inside the launcher. Bootstrap additionally starts an isolated child interpreter with inherited
`PYTHONPATH` removed and Python's unsafe-path behavior disabled, then verifies the actually imported
`portfolio_common` module resides under the invoking worktree.

Remote Feature Lane `29977029134` proved that PEP 610 `direct_url.json` is not a portable execution
contract for this bootstrap: pip built and installed the editable package successfully on Linux,
but the subsequent metadata lookup exposed no direct-URL payload. The isolated import-origin proof
replaces that metadata assumption while remaining fail-closed for a missing or foreign install.

Independent exact-head review then reproduced the same ownership defect for the generic service
package name `app`: the launcher exited successfully while loading a physical user-site package and
editable finder mappings from another Core worktree. Proving only `portfolio_common` at launcher
entry was therefore insufficient for commands that import a service package later.

The launcher now prepends a repository-owned Python startup hook. Before the delegated command
runs, that hook removes editable finders that can claim `app` or `portfolio_common` from outside the
invoking checkout and installs an actual-import fence for both protected names. A physical package
found through normal site-package lookup fails closed with expected and resolved paths. Explicitly
selecting one service-local root continues to load that checkout's `app`; unrelated third-party
packages and paths remain available.

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

- 23 focused warning-strict launcher, bootstrap, and pinned-tool tests passed after the review fix.
- A two-root subprocess regression loaded distinguishable current source despite an inherited
  foreign worktree path and preserved child exit behavior without a shell.
- A real child interpreter with a physical foreign `app` installed in its user site now fails
  closed, and a synthetic PEP 660 finder mapped to another worktree is removed before delegation.
- The independent review reproduction now exits non-zero for the ambient foreign `app`; an
  explicitly selected current ingestion-service root imports successfully.
- Windows local proof resolved
  `C:\Users\Sandeep\projects\lotus-core-demo-pack-wt\src\libs\portfolio-common\portfolio_common\__init__.py`.
- `make quality-workflow-governance-gate`, `make transaction-capability-catalog-guard`, and
  `make api-vocabulary-gate` passed through the launcher.
- The complete strict `make architecture-guard` chain passed through the launcher.
- Strict MyPy passed for all three touched source modules; touched Ruff and diff hygiene passed.
- A complete local `make install-ci` passed and the isolated post-install interpreter resolved the
  shared package from this worktree.

GitHub Actions Linux proof, broad lint/type/test lanes, merge, exact-main validation, and
branch/worktree reconciliation remain delivery gates rather than local claims.
