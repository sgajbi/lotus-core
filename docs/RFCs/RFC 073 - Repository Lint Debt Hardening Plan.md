# RFC 073 - Repository Lint Debt Hardening Plan

| Field | Value |
| --- | --- |
| Status | Proposed |
| Created | 2026-03-05 |
| Last Updated | 2026-03-05 |
| Owners | lotus-core engineering |
| Depends On | RFC-029 engineering baseline; RFC-066 production-readiness discipline |
| Related Standards | CI quality gates; modularity and maintainability standards |
| Scope | In repo |

## Executive Summary
This RFC defines a controlled, non-disruptive burn-down plan for repository-wide Ruff debt so that code quality reaches a sustainable institutional standard without blocking active transaction RFC delivery.

The plan runs as a dedicated stream in parallel with feature RFCs and uses strict scope boundaries to avoid mixing large hygiene changes into functional slices.

## Baseline (2026-03-05)
1. Full-repo Ruff run reports significant pre-existing violations (import order, line length, unused imports).
2. RFC-070/071 governance and test gates are passing, but repo-wide lint debt remains a structural maintenance risk.
3. Current workflows rely on targeted lint in active domains rather than a fully clean global baseline.

## Goals
1. Establish predictable, incremental lint hardening with measurable progress.
2. Avoid regressions by preventing new lint debt in already-cleaned domains.
3. Improve modular readability and long-term maintainability.
4. Keep feature throughput by avoiding mega-format PRs.

## Non-Goals
1. No broad behavior refactors in lint-only slices.
2. No forced repo-wide reformat in one change.
3. No blocking of urgent functional fixes while debt reduction is in progress.

## Delivery Slices

### Slice 0 - Baseline and Ownership Map
Deliverables:
1. Snapshot current Ruff debt by top-level domain (`src/services/*`, `src/libs/*`, `tests/*`, `scripts/*`).
2. Assign owners and order by risk/runtime criticality.
3. Publish burn-down tracker in docs.

Exit Criteria:
1. Baseline inventory and owner map are documented and accepted.

### Slice 1 - Runtime-Critical Services
Deliverables:
1. Resolve Ruff violations in runtime-critical services and shared libraries touched by transaction flows.
2. Keep changes behavior-neutral and test-backed.
3. Add targeted lint gate(s) for cleaned domains.

Exit Criteria:
1. Cleaned runtime domains remain Ruff-clean.
2. Functional regression suite for affected domains passes.

### Slice 2 - Core Test Domains
Deliverables:
1. Resolve Ruff violations in high-value unit/integration suites.
2. Normalize long test lines/imports/unused fixtures with readability-first edits.
3. Keep tests deterministic and semantically unchanged.

Exit Criteria:
1. Cleaned test domains remain Ruff-clean.
2. Suite pass-rate unchanged.

### Slice 3 - Scripts and Tooling
Deliverables:
1. Resolve Ruff debt in `scripts/` and quality tooling.
2. Ensure script behavior remains unchanged through targeted script tests or dry-run checks.

Exit Criteria:
1. Governance tooling remains operational and Ruff-clean in cleaned subdomains.

### Slice 4 - Global Gate Tightening
Deliverables:
1. Expand CI lint scope progressively to include cleaned domains by default.
2. Document escalation rule for newly introduced lint debt.
3. Publish closure report with remaining debt (if any) and target date for full clean.

Exit Criteria:
1. CI enforces new baseline.
2. Residual debt is explicitly owned and scheduled.

## Operating Rules
1. Lint slices are separate from feature slices by default.
2. No functional behavior change is allowed in lint-only PRs.
3. Each lint slice must include:
 - before/after error counts
 - impacted domain list
 - verification commands and outcomes
4. If a lint fix requires behavior change, split it into a separate functional RFC slice.

## Validation Strategy
For each lint slice:
1. `python -m ruff check <targeted domains>`
2. `make typecheck` for impacted modules
3. targeted pytest for impacted modules
4. Full-repo Ruff snapshot trend report in closure notes

## Risks and Mitigations
1. Risk: high churn and merge conflicts.
 - Mitigation: small domain-bounded batches and short-lived branches.
2. Risk: accidental behavior changes in test/script cleanup.
 - Mitigation: strict lint-only scope and mandatory targeted regressions.
3. Risk: prolonged debt backlog.
 - Mitigation: explicit owner map, milestone dates, and CI guard tightening by slice.

## Approval Gate
Implementation starts after approval of:
1. slice sequence and domain ownership;
2. CI tightening strategy;
3. acceptance of parallel execution with transaction RFC stream.
