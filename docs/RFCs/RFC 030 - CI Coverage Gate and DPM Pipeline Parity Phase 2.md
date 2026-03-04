# RFC 030 - CI Coverage Gate and lotus-manage Pipeline Parity Phase 2

- Status: Proposed
- Date: 2026-02-23
- Depends on: RFC 029

## Context

RFC 029 established a lotus-manage-style baseline, but CI remained basic in two areas:

- no matrixed test suites with artifactized coverage data
- no explicit combined coverage gate

Also, some integration tests currently depend on full Docker orchestration and are not yet stable for mandatory CI gates.

## Decision

Adopt lotus-manage-style phased CI hardening:

1. Add test matrix jobs:
   - `Tests (unit)`
   - `Tests (integration-lite)`
2. Upload per-suite coverage artifacts.
3. Add `Coverage Gate (Combined)` job enforcing `--fail-under=84`.
4. Keep `Lint, Typecheck, Unit Tests` and `Validate Docker Build` as protected required checks.
5. Keep Docker-dependent integration tests out of required gate until migration-runner/docker-compose reliability is hardened.

## Why 84% Now

- Current stable combined scope (unit + integration-lite) reaches ~85% with expanded router tests.
- 84% creates a real guardrail without introducing CI flakiness.
- Threshold can be ratcheted upward once additional routers/services and Docker-dependent integration tests are stabilized.

## Makefile Alignment

Add standardized commands:

- `make test-integration-lite`
- `make coverage-gate`
- `make ci-local`

This keeps local validation aligned with GitHub Actions.

## Next Ratchet (Phase 3)

1. Fix Docker-dependent integration failures in CI (`migration-runner`/env wiring).
2. Promote selected integration tests into required matrix.
3. Raise combined coverage gate to `85%+`.
4. Introduce full-suite coverage gating once non-determinism is removed.
