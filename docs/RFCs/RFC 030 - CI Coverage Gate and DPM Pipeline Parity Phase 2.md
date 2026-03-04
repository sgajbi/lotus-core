# RFC 030 - CI Coverage Gate and DPM Pipeline Parity Phase 2

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-02-23 |
| Last Updated | 2026-03-04 |
| Owners | Platform engineering, CI governance |
| Depends On | RFC 029 |
| Scope | Matrixed test execution, coverage artifact flow, combined coverage enforcement |

## Executive Summary

RFC 030 moved CI from baseline checks to stronger suite partitioning and coverage enforcement.
Current implementation is present and, in some aspects, stricter than originally proposed:
1. Matrixed suites are active.
2. Coverage artifacts are uploaded per suite and combined in gate job.
3. Combined coverage threshold is enforced at `99` (higher than RFC text’s `84`).

## Original Requested Requirements (Preserved)

Original RFC 030 requested:
1. Add matrix test jobs (`unit`, `integration-lite`).
2. Upload per-suite coverage artifacts.
3. Add combined coverage gate with `--fail-under=84`.
4. Keep docker-dependent unstable suites outside required baseline while hardening continues.
5. Align local make commands (`test-integration-lite`, `coverage-gate`, `ci-local`).

## Current Implementation Reality

Implemented:
1. CI test matrix runs multiple suites (unit, unit-db, integration-lite, ops-contract, buy-rfc, sell-rfc).
2. Coverage artifacts per suite uploaded and merged in dedicated `Coverage Gate (Combined)` job.
3. Combined coverage gate enforces `--fail-under=99`.
4. Makefile includes `test-integration-lite`, `coverage-gate`, and `ci-local` commands.

Operational note:
1. Docker-dependent gates exist as additional jobs; required-check policy is repository governance outside this file.

Evidence:
- `.github/workflows/ci.yml`
- `Makefile`
- `scripts/coverage_gate.py`
- `scripts/test_manifest.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Matrix test jobs | Implemented (expanded matrix) | `ci.yml` |
| Coverage artifact upload | Implemented | `ci.yml` |
| Combined coverage gate | Implemented, stricter threshold (`99`) | `ci.yml` |
| Local command parity | Implemented | `Makefile` |
| Keep unstable docker-dependent tests out of core mandatory path | Partially governance-dependent; additional jobs exist with conditional triggers | `ci.yml` |

## Design Reasoning and Trade-offs

1. Artifact-based coverage merge improves auditability and deterministic gating.
2. Higher threshold raises quality bar but can increase PR friction if scope/test stability drifts.
3. Expanded suite matrix gives broader confidence while keeping suite segmentation manageable.

## Gap Assessment

No material implementation gap in repository for RFC 030 intent; enforcement policy of which checks are mandatory remains branch-protection governance.

## Deviations and Evolution Since Original RFC

1. Coverage threshold is stronger than original proposal (`99` vs `84`).
2. Matrix scope broadened beyond original two-suite plan.

## Proposed Changes

1. Keep RFC 030 as `Fully implemented and aligned` with documented threshold evolution.
2. Maintain explicit rationale for elevated threshold in CI docs to avoid confusion with original RFC text.

## Test and Validation Evidence

1. CI matrix and coverage gate job definitions:
   - `.github/workflows/ci.yml`
2. Local parity commands:
   - `Makefile`
3. Coverage gate utility and suite manifest:
   - `scripts/coverage_gate.py`, `scripts/test_manifest.py`

## Original Acceptance Criteria Alignment

Core acceptance criteria are met and exceeded on threshold strictness.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. Should the RFC explicitly record the date and rationale for moving from `84` to `99` to preserve policy lineage?

## Next Actions

1. Keep threshold and suite-partition contracts stable unless an explicit governance RFC changes them.
2. Continue hardening docker-dependent suites for predictable inclusion in required-check policy.
