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
port until startup. `compose_up(...)` receives the runtime reservation, releases it immediately
before Docker claims the ports, and replaces the complete dynamic port generation after a
recognized bind conflict. Exhausted retries report `host_port_bind_conflict`, attempt count,
reallocation count, and Compose project identity.

Do not restore free-port probing that closes sockets before startup, preallocate child-suite ports
in `test_manifest.py`, or retry a bind conflict with unchanged dynamic assignments. Preserve fixed
port environment values only for explicit operator-controlled runtimes.

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
