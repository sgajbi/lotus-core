# RFC 073 - Repository Lint Debt Hardening Plan

| Field | Value |
| --- | --- |
| Status | In Progress |
| Created | 2026-03-05 |
| Last Updated | 2026-03-05 |
| Owners | lotus-core engineering |
| Depends On | RFC-029 engineering baseline; RFC-066 production-readiness discipline |
| Related Standards | CI quality gates; modularity and maintainability standards |
| Scope | In repo |

## Executive Summary
This RFC defines a controlled, non-disruptive burn-down plan for repository-wide Ruff debt so that code quality reaches a sustainable institutional standard without blocking active transaction RFC delivery.

The plan runs as a dedicated stream in parallel with feature RFCs and uses strict scope boundaries to avoid mixing large hygiene changes into functional slices.

## Slice Execution Status
| Slice | Status | Evidence |
| --- | --- | --- |
| 0 | Completed | `docs/RFCs/RFC-073-SLICE-0-LINT-BASELINE.md` |
| 1 | In Progress | `python -m ruff check src/services/calculators src/services/persistence_service src/libs/portfolio-common src/libs/financial-calculator-engine --statistics` (before/after snapshot below) |
| 2 | Pending | Core test-domain lint burn-down |
| 3 | Pending | Scripts/tooling lint burn-down |
| 4 | Pending | CI/global gate tightening |

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

Slice 0 Completion Notes:
1. Baseline inventory is published in `docs/RFCs/RFC-073-SLICE-0-LINT-BASELINE.md`.
2. Rule-distribution and domain-distribution counts are captured using deterministic `ruff --statistics` commands.
3. Execution order for burn-down is set to:
 - `tests` (highest volume),
 - `src/services`,
 - `src/libs`,
 - `scripts`.

### Slice 1 - Runtime-Critical Services
Deliverables:
1. Resolve Ruff violations in runtime-critical services and shared libraries touched by transaction flows.
2. Keep changes behavior-neutral and test-backed.
3. Add targeted lint gate(s) for cleaned domains.

Exit Criteria:
1. Cleaned runtime domains remain Ruff-clean.
2. Functional regression suite for affected domains passes.

Slice 1 Progress (Batch 1):
1. Scope completed:
 - `src/services/calculators`
 - `src/services/persistence_service`
 - `src/libs/portfolio-common`
 - `src/libs/financial-calculator-engine`
2. Actions:
 - applied safe lint-only fixes for `I001`, `F401`, `F841`
 - manual cleanup of one residual unused local variable in position consumer
3. Snapshot:
 - before: `244 E501`, `73 I001`, `29 F401`, `3 F841`, `1 E402`, `1 E711`, `1 F541`
 - after: `239 E501`, `1 E402`, `1 E711`, `1 F541`
 - removed in batch: `105` findings (`I001/F401/F841` fully eliminated in scope)
4. Regression evidence:
 - `make typecheck` -> passed
 - `python scripts/test_manifest.py --suite interest-rfc --quiet` -> `113 passed`

Slice 1 Progress (Batch 2):
1. Resolved remaining non-E501 issues in runtime-critical scope:
 - `E402`, `E711`, `F541`, and residual `I001`
2. Post-batch runtime-critical snapshot:
 - `238 E501` remaining
 - `0` remaining for `I001/F401/F841/E402/E711/F541`
3. Regression evidence:
 - `make typecheck` -> passed
 - `python scripts/test_manifest.py --suite interest-rfc --quiet` -> `113 passed`

Slice 1 Progress (Batch 3):
1. Scoped E501 reduction completed for persistence runtime + integration boundary files:
 - `src/services/persistence_service/app/consumer_manager.py`
 - `src/services/persistence_service/app/consumers/*` (selected)
 - `src/services/persistence_service/app/repositories/*` (selected)
 - `src/services/persistence_service/tests/integration/test_repositories.py`
2. Scope method:
 - `ruff format` on selected files, followed by manual wrapping for remaining long literals/comments
3. Snapshot impact:
 - runtime-critical scope E501 count: `238 -> 216` (`-22`)
4. Regression evidence:
 - `make typecheck` -> passed
 - `python scripts/test_manifest.py --suite interest-rfc --quiet` -> `113 passed`

Slice 1 Progress (Batch 4):
1. Scoped E501 reduction completed for financial-calculator-engine core/modeling chunk:
 - `src/libs/financial-calculator-engine/src/core/models/request.py`
 - `src/libs/financial-calculator-engine/src/core/models/transaction.py`
 - `src/libs/financial-calculator-engine/src/logic/cost_basis_strategies.py`
2. Scope method:
 - `ruff format` on selected files, followed by manual wrapping of residual long descriptions/messages
3. Snapshot impact:
 - runtime-critical scope E501 count: `216 -> 188` (`-28`)
4. Regression evidence:
 - `make typecheck` -> passed
 - `python scripts/test_manifest.py --suite interest-rfc --quiet` -> `113 passed`

Slice 1 Progress (Batch 5):
1. Scoped E501 reduction completed for valuation-consumer runtime hotspot:
 - `src/services/calculators/position_valuation_calculator/app/consumers/valuation_consumer.py`
2. Scope method:
 - `ruff format` on the file, followed by manual wrapping of residual long log/error/comment lines
3. Snapshot impact:
 - runtime-critical scope E501 count: `188 -> 164` (`-24`)
4. Regression evidence:
 - `make typecheck` -> passed
 - `python scripts/test_manifest.py --suite interest-rfc --quiet` -> `113 passed`

Slice 1 Progress (Batch 6):
1. Scoped E501 reduction completed for valuation repository hotspot:
 - `src/services/calculators/position_valuation_calculator/app/repositories/valuation_repository.py`
2. Scope method:
 - `ruff format` on file (no manual follow-up needed)
3. Snapshot impact:
 - runtime-critical scope E501 count: `164 -> 150` (`-14`)
4. Regression evidence:
 - `make typecheck` -> passed
 - `python scripts/test_manifest.py --suite interest-rfc --quiet` -> `113 passed`

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
