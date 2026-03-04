# RFC 029 - lotus-manage Engineering Baseline Alignment

- Status: Proposed
- Date: 2026-02-23
- Owner: Platform Engineering

## Context

`lotus-core` currently lacks a consistent top-level engineering baseline compared to `lotus-advise`:

- no repository-level CI workflow for lint/typecheck/tests/docker
- no repository-level `Makefile` standard commands
- no repository-level `mypy.ini`
- inconsistent linting and formatting execution path
- no PR auto-merge workflow aligned with protected branch delivery

This slows delivery and increases integration risk across platform services.

## Decision

Adopt a lotus-manage-style baseline now, with a phased strictness model:

1. Add unified CI workflow with:
   - workflow lint
   - lint + typecheck + unit tests
   - docker build validation
2. Add repo `Makefile` with:
   - `install`, `lint`, `typecheck`, `test`, `check`, `docker-build`
3. Add repo `mypy.ini` and `ruff` config in `pyproject.toml`
4. Add PR auto-merge workflow matching lotus-manage pattern
5. Apply `main` branch protection requiring CI checks and PR review

## Phase Strategy

### Phase 1 (this RFC implementation)

- enforce quality gates on stable slice:
  - `src/services/query_service/app`
  - `tests/unit/services/query_service`
- enforce mypy on:
  - `src/services/query_service/app/dtos`
  - `src/services/query_service/app/routers`
- temporary lint exception for `E701` to avoid blocking migration on legacy style debt

### Phase 2 (next RFC)

- expand lint/typecheck scope to additional services/libs
- remove `E701` exception
- add integration/e2e pipeline partitioning and coverage gates

## Consequences

### Positive

- immediate CI and quality standardization with lotus-manage-compatible workflow shape
- deterministic local commands for developers and AI agents
- reduced drift in tooling across backend repositories

### Trade-Off

- initial enforcement is intentionally scoped (not full-repo strict yet)
- strictness ratchet is planned, not completed in a single change

## Success Criteria

- CI runs on all PRs and pushes to `main`
- `make check` succeeds locally and in CI
- Docker build check succeeds in CI
- `main` branch protection enabled with required checks

## Out of Scope

- full-repo lint debt cleanup
- full-repo mypy adoption
- e2e docker-compose CI parity for all services in this change

