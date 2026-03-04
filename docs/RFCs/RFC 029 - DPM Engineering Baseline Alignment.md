# RFC 029 - DPM Engineering Baseline Alignment

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-02-23 |
| Last Updated | 2026-03-04 |
| Owners | Platform engineering, repository governance |
| Depends On | lotus-platform CI/dev workflow standards |
| Scope | Repository baseline alignment for CI, Make commands, lint/typecheck scaffolding |

## Executive Summary

RFC 029 established the repository engineering baseline (CI + local command parity + typed/linted entry points).
Current implementation is in place and materially exceeds the initial Phase 1 scope in some areas.

Key baseline components now exist:
1. Repository-level CI workflow with quality gates and test jobs.
2. Standardized top-level `Makefile` commands.
3. Repository-level `mypy.ini` and ruff config in `pyproject.toml`.
4. Expanded CI contract and gating beyond initial minimal baseline.

## Original Requested Requirements (Preserved)

Original RFC 029 requested:
1. Add unified CI workflow for lint/typecheck/tests/docker validation.
2. Add standard `Makefile` developer commands.
3. Add repo mypy + ruff baseline.
4. Align with phased strictness model from scoped paths toward broader enforcement.
5. Apply branch/merge governance alignment (outside repo code where applicable).

## Current Implementation Reality

Implemented in repository:
1. `.github/workflows/ci.yml` defines workflow lint, quality, test suites, coverage gate, docker build, smoke/performance/recovery gates.
2. `Makefile` exposes install/lint/typecheck/test/check/coverage/docker and additional standardized QA gates.
3. `mypy.ini` exists and scopes typed enforcement to selected query-service paths.
4. `pyproject.toml` includes ruff settings and pytest config.

Notes:
1. Branch protection / PR auto-merge policy is org/repo-hosting configuration; not directly auditable from source tree.
2. CI scope has evolved beyond initial Phase 1 and integrates broader quality controls.

Evidence:
- `.github/workflows/ci.yml`
- `Makefile`
- `mypy.ini`
- `pyproject.toml`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Unified CI baseline | Implemented and expanded | `ci.yml` |
| Standard Make targets | Implemented | `Makefile` |
| Repo mypy + ruff baseline | Implemented | `mypy.ini`; `pyproject.toml` |
| Scoped strictness-first rollout | Implemented via typed scope + matrixed gates | `mypy.ini`; CI workflow |
| Branch protection/automerge governance | External to codebase | platform/repo settings |

## Design Reasoning and Trade-offs

1. Scoped strictness prevents blocking delivery while quality baseline is established.
2. Standard make targets create deterministic local/CI parity for developers and agents.
3. Expanded CI gates strengthen reliability but increase runtime/resource usage.

## Gap Assessment

No material in-repo implementation gap remains for RFC 029 baseline intent.

## Deviations and Evolution Since Original RFC

1. CI pipeline evolved beyond original narrow baseline (additional gates and suites).
2. Coverage threshold in CI moved under RFC 030 evolution with tighter enforcement.

## Proposed Changes

1. Keep RFC 029 as `Fully implemented and aligned` for baseline objective.
2. Continue strictness ratchet and policy hygiene in later RFC streams.

## Test and Validation Evidence

1. Workflow definitions and quality jobs in `ci.yml`.
2. Reproducible local commands in `Makefile`.
3. Typed/lint config in `mypy.ini` and `pyproject.toml`.

## Original Acceptance Criteria Alignment

In-repo acceptance criteria are met.
Branch protection verification remains governance/admin concern outside source code.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should we add a repository-visible governance checklist file that records required branch protection and required checks to close the auditability gap?

## Next Actions

1. Maintain current baseline.
2. Continue incremental expansion of strict typing/lint scope under future RFC loops.
