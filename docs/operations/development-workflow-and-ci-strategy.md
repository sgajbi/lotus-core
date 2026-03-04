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
3. Enable auto-merge only after all required checks are green.

## CI Gate Tiers

### Tier 1: Fast PR Gates (blocking)
Run on every PR and push to `main`:
1. Lint and typecheck.
2. Unit and core integration tests.
3. Docker smoke contract.
4. Latency gate.
5. Performance load gate (fast tier).

Goal: quick, meaningful confidence for developer velocity.

### Tier 2: Full Institutional Gates (heavy)
Run on schedule, manual dispatch, and mainline validation:
1. Performance load gate (full tier, heavy replay and drain invariants).
2. Additional endurance/performance validation as added by future RFC slices.

Goal: production-readiness evidence without slowing every PR loop.

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
