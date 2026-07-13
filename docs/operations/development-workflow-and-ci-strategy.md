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

## CI Gate Tiers

### Tier 1: Fast PR Gates (blocking)
Run on every PR and push to `main`:
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

PR Merge Gate and Main Releasability each build one governed runtime image set after coverage
passes. The existing `Validate Docker Build` job is the sole producer for that workflow SHA:

1. `prebuild_ci_images.py` builds the ordered service union once, coalesces identical Dockerfiles,
   and writes per-service timing evidence.
2. `runtime_image_set.py create` exports one portable Docker bundle and a manifest containing the
   source commit, branch, repository, CI run, generated-at time, service image IDs, Dockerfile
   hashes, compose hash, dependency-lock hash, dependency-closure hash, bundle digest, and content
   hash.
3. Docker-backed jobs download the same one-day transport artifact and run `load-verify` against
   `GITHUB_SHA` before installing or starting the stack.
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
