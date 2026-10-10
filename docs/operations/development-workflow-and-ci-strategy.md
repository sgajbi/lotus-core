# Lotus-Core Development Workflow and CI Strategy

## Objective
Define a repeatable, single-developer-friendly workflow that preserves institutional engineering quality while keeping feedback loops fast.

## Branching Model
1. Create one feature branch per RFC or implementation slice from `main`.
2. Use descriptive names:
- `feat/rfc-066-slice-b-load-gate`
- `fix/rfc-066-load-gate-drain-invariant`
- `chore/workflow-ci-hardening`
3. Never commit directly to `main`.

## Commit Model
1. Make small, scope-focused commits.
2. Push frequently to avoid large divergence and reduce rework risk.
3. Keep commits coherent so each one is reversible and auditable.

## PR Model (Single Developer)
1. PR is mandatory, even without reviewer approval requirements.
2. Treat PR checks as the quality approval layer.
3. Enable auto-merge only on protected branches and only for PRs explicitly labeled `automerge`.
4. Missing the `automerge` label must be a successful no-op, not a skipped required-check signal.
   Removing the label prevents this workflow from issuing a new queue request; it does not disable
   GitHub auto-merge after it has already been enabled. Use `gh pr merge --disable-auto <pr>` or
   the GitHub UI to cancel an already-enabled auto-merge request.
5. The `automerge` label is metadata for `.github/workflows/pr-auto-merge.yml` only. Adding it while
   the protected PR Merge Gate is running must not start or cancel that full gate for the unchanged
   head SHA. Apply it whenever the PR is ready to queue; existing exact-head checks remain valid.
6. A `synchronize` event is different: it means the PR head changed. The PR Merge Gate must validate
   the new head and may cancel stale work for the prior PR ref. Opened, reopened, and
   ready-for-review events enter the governed gate with fresh classification; broader same-head evidence reuse for
   those lifecycle events remains separately governed.
7. PR Auto Merge uses the repository-scoped `LOTUS_AUTOMERGE_TOKEN` under read-only workflow
   permissions. When that credential is absent, the workflow warns and stops; it never falls back
   to `github.token`, whose merges can suppress the post-merge evidence workflow.
8. Every rebase-merged PR dispatches Main Releasability once per landed revision through immutable
   `main-releasability-<revision_sha>` tags. Exact range, count, ancestry and PR patch identity fail
   closed before dispatch. The main workflow validates each exact SHA, proves it is reachable from
   `main`, and never cancels another revision's evidence run.
9. `make main-gate-coverage-audit` is the scheduled/manual backstop. It audits the complete
   post-enforcement range, retains exact run identities and terminal outcomes, and fails on missing
   or unverifiable coverage rather than treating a cancelled or pending run as a verdict.

## CI Gate Tiers

### Tier 1: Fast PR Gates (blocking)
Run on every PR and every exact merged `main` revision:
1. Lint and typecheck.
2. Unit and core integration tests.
3. Docker smoke contract.
4. Latency gate.
5. Performance load gate (fast tier).

Replay-storm drain is complete only when the transaction-processing duplicate outcome counter
advances by the submitted replay count. A semantic duplicate reuses its existing `processed_events`
record, so row growth is not a valid replay-completion signal. DLQ pressure, backlog pressure, and
drain completion remain enforced independently.

Goal: quick, meaningful confidence for developer velocity.

### Tier 2: Full Institutional Gates (heavy)
Run on schedule, manual dispatch, and mainline validation:
1. Performance load gate (full tier, heavy replay and drain invariants).
2. Additional endurance/performance validation as added by future RFC slices.

Goal: production-readiness evidence without slowing every PR loop.

## Exact-Source Runtime Image Sets

Documentation-only PRs use conservative source classification as described below and produce no
runtime images, image SBOM or build provenance. Full PR and every main/release run retain the
existing exact-source image and security certification; omitted cohorts never mint fake evidence.

## Conservative PR Change Selection

`scripts/quality/change_classification.py` owns one merge-base diff classifier. Its explicit
allowlist covers regular non-executable authored Markdown in the named documentation directories,
the wiki, README, changelog and repository engineering context. `docs/standards/`, contracts,
generated documentation inputs, arbitrary Markdown locations and non-Markdown files are full.
Renames, copies, deletions, type changes, symlinks, executable documents, empty diffs and unknown
paths are full. Application, shared-library, test, migration, API/event/schema, dependency, build,
workflow and classifier/guard changes retain every applicable runtime cohort. Per-service selection
is deferred to the ownership split in [#462](https://github.com/sgajbi/lotus-core/issues/462).

A workflow can omit runtime work only for a verified `pull_request` in the canonical merge gate.
The event base/source, actual checkout, tree, merge-base, repository, workflow, run, attempt and job
are recorded. A source checkout or its exact base/source synthetic merge must match; missing refs,
dirty tracked files, unexpected context or identity mismatch select full. Every synchronize event
recomputes the decision; an older receipt or environment mode flag cannot authorize omission.

All 39 app-bound required contexts still run their own unconditional jobs and enforcement steps.
Fixed `pr-*` Make targets execute the original full native target for source changes. For a proved
documentation-only diff, they run the documentation/wiki/catalog guard, `make docs-evidence-pack`
and, for test matrix entries, the corresponding native collection selector, then report
`omit-runtime-docs-only`. The native documentation evidence pack is retained inside each successful
selection receipt. Full unit, DB,
coverage aggregation, image build and runtime/E2E execution are omitted only by that verified path.
The static security/dependency checks and Quality Baseline governance jobs remain enabled.
`output/pr-validation/*.json`, uploaded per exact run/head/job, and job summaries record reasons,
selected commands and native exits. Conditional downloads only omit artifacts that this same
classification intentionally did not create; no required enforcement step is conditional.

Every selecting PR job installs application and tooling dependencies with `make install-ci`
before enforcement, including the Docker-build job. The documentation pack imports application
schemas for its API vocabulary and route-catalog checks; tooling-only installation cannot prove
those checks. The workflow contract rejects missing, conditional, tooling-only or late installation.

Merge/Main full-unit execution and the zero-warning budget have one owner, `coverage-shard-unit`;
combined coverage still enforces its unchanged thresholds. The redundant serial static warning
execution is removed. Original local Make targets and all main/scheduled/release/security,
SBOM/provenance/image certification stay full. Feature push validation defers only after positively
observing an open main-targeting PR and canonical required PR run for the exact head. Otherwise it
retains its original full-unit warning and DB producers, including on API error, cancellation,
wrong head/base or ambiguous authority. A PR opened after Feature fallback begins can overlap;
this conservative race is not hidden or counted as universal deduplication.

From the repository root, in PowerShell:

```powershell
python scripts/development/repository_python.py scripts/quality/change_classification.py --base origin/main --head HEAD
make change-classification-guard quality-workflow-governance-gate
```

From the repository root, in Bash:

```bash
python scripts/development/repository_python.py scripts/quality/change_classification.py --base origin/main --head HEAD
make change-classification-guard quality-workflow-governance-gate
```

The explicit local range command is diagnostic; workflow omission uses the verified event path.
The Make authority guard follows each registered PR wrapper into its same-named native full target,
so changing a wrapped build/coverage recipe cannot escape the existing exact command contract.
Guard controls exercise valid and damaged workflow/Make inputs. Miniature subprocess fixtures run
the unchanged native unit/warning/coverage owner with real passing, failing and warning cases;
they supplement the full source-change PR producer rather than substituting mock composition.

Closure evidence must include a live documentation-only PR and representative full source-change
PR, all required contexts, receipts for each omitted/selected cohort, actual main and wiki parity.
Measure wall duration and summed job runner duration from named successful runs and exact sources;
report setup/queue differences and the Feature fallback race. Summed hosted job time is not a
precise billable-minute claim. A lower job count or mocked producer alone does not establish
[full #749 acceptance](https://github.com/sgajbi/lotus-core/issues/749).

## Runtime Image Certification

Full PR validation and Main Releasability each build one governed runtime image set after coverage
passes. The existing `Validate Docker Build` job is the sole producer for that workflow SHA:

1. `prebuild_ci_images.py` builds the ordered service union once, coalesces identical Dockerfiles,
   and writes per-service timing evidence.
2. `runtime_image_set.py create` exports one portable Docker bundle and a manifest containing the
   source commit, branch, repository, CI run, generated-at time, service image IDs, Dockerfile
   hashes, compose hash, dependency-lock hash, dependency-closure hash, bundle digest, and content
   hash.
3. Docker-backed jobs download the same one-day transport artifact. Every consuming Make control
   declares `runtime-image-set-load-verify` as a prerequisite. Its checked Python orchestrator
   verifies against `GITHUB_SHA` and writes the exact-head receipt only after success, so workflow
   ordering or shell failure masking cannot bypass the handoff.
4. Verification fails before test execution on source-SHA, bundle, manifest, dependency, image-ID,
   or OCI-label mismatch.

The portable bundle is ephemeral CI transport and is never a release or environment-promotion
image. CI-only release publication, vulnerability scanning, signing, attestation, and digest-based
deployment remain owned by `.github/workflows/image-release.yml`.

## Concurrent Compose Isolation

Repository-native Compose suites prepare a unique project and hold every dynamically assigned host
port until startup. `compose_up(...)` receives the complete `PreparedTestRuntime` so project name,
subprocess environment, current endpoints, and reservation ownership cannot drift. It releases the
reservation immediately before Docker claims the ports and replaces the complete dynamic port
generation after a recognized bind conflict. Exhausted retries report
`host_port_bind_conflict`, attempt count, reallocation count, and Compose project identity.

The root pytest session owns its prepared runtime even when no Docker-backed fixture is selected.
Its session-finish hook releases every still-held reservation, while the `docker_services` finalizer
uses the same idempotent release path before project-scoped Compose teardown. Unit-only and
collection-only commands must therefore finish without interpreter-finalizer `unclosed socket`
warnings. Do not move reservation cleanup exclusively into a Docker fixture or rely on garbage
collection/process exit to close bound ports.

When a local gate requests image builds, the helper runs `docker compose build` while host-port
reservations are still active, then starts the services without `--build` immediately after
release. This keeps image-build duration outside the bind-race interval and avoids repeating a long
build after a recoverable collision.

Do not restore free-port probing that closes sockets before startup, preallocate child-suite ports
in `test_manifest.py`, mutate shared process environment for same-process concurrent projects, or
retry a bind conflict with unchanged dynamic assignments. Preserve fixed port environment values
only for explicit operator-controlled runtimes.

Latency, performance-load, institutional-completion, failure-recovery, and endpoint-smoke use
`ManagedComposeRun`.
The managed owner removes inherited parent-runtime ports, preserves explicit local endpoint URL
overrides, prepares a unique project, starts through `compose_up(...)`, captures project-identified
logs, and tears down before returning. Use `--skip-compose` for an already-running external target
and the driver-specific keep-stack option only for explicit local diagnosis.

CI uploads `output/task-runs/diagnostics/*.log` produced by the lifecycle owner. Do not add a
post-run `docker compose logs` step: after managed teardown it addresses the wrong implicit project
and can overwrite useful evidence with an empty artifact.

Failure recovery uses the `integration` runtime profile. Its migration-runner polling,
interruption-service lookup, database/Kafka/HTTP endpoints, and diagnostic artifact must remain
bound to that runtime's exact project. `--skip-compose` preserves an explicitly named external
project and `--keep-stack-up` is the only supported local post-run inspection path.
Recovery reports expose each transaction, cost, cashflow, position, claim, and consumer-lag
predicate with actual value, target, comparison, satisfaction, and source UTC last-change time.
Retain these fields when extending recovery conditions so timeout evidence identifies what stopped
changing rather than returning only a generic timeout.
Exact-count overshoot and DLQ growth relative to the pre-interruption baseline are terminal. The
gate records the source-safe terminal reason and exits polling immediately instead of consuming the
remaining timeout budget.
The DLQ baseline and terminal delta come from durable `consumer_dlq_events` rows filtered by the
exact transaction consumer group and source topic. Do not default an absent readiness field to zero;
the transaction readiness contract does not own DLQ-count evidence.
The recovery driver no longer accepts `--ops-token`: it does not call an operations-authenticated
health endpoint, and retaining an ignored credential would misrepresent the gate's evidence path.

## Merge and Hygiene Rules
1. Merge only when required checks are green.
2. After merge:
- delete remote feature branch
- delete local feature branch
- `checkout main` and `pull --ff-only`
3. End-state must always be: `local = remote = main`.

## Operational Evidence in PRs
Every PR should include:
1. What changed.
2. Why it changed.
3. Exact validation commands run locally.
4. Any known follow-up work or constraints.

## Escalation Rules
1. If a gate is flaky, fix the gate or isolate it to non-blocking scheduled execution.
2. If a required gate fails repeatedly, do not merge; perform fix-forward.
3. If the change impacts contracts or governance, include corresponding RFC/doc updates in the same PR.
