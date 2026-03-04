# RFC 053 - Enforce 99 Percent Query Service Coverage Gate

| Metadata | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-02-24 |
| Last Updated | 2026-03-04 |
| Owners | query-service quality gates |
| Depends On | RFC 052 |
| Scope | Raise enforced combined coverage floor to 99% |

## Executive Summary

RFC 053 is implemented.
Coverage gate threshold is set to 99 in the coverage gate script.

Classification: `Fully implemented and aligned`.

## Original Requested Requirements (Preserved)

Original RFC 053 requested:
1. Raise coverage gate threshold from 95 to 99.
2. Enforce higher quality floor in CI/local gate.

## Current Implementation Reality

Implemented:
1. `scripts/coverage_gate.py` sets `FAIL_UNDER = "99"`.
2. Gate combines unit + integration-lite coverage and reports with this threshold.

Evidence:
- `scripts/coverage_gate.py`

## Requirement-to-Implementation Traceability

| Original Requirement | Current Implementation in lotus-core | Evidence |
| --- | --- | --- |
| Raise fail-under threshold to 99 | Implemented | `coverage_gate.py` constant |
| Enforced combined coverage gate | Implemented | coverage combine/report flow in script |

## Design Reasoning and Trade-offs

1. Higher threshold prevents coverage regression after hardening waves.
2. Faster CI failure on under-tested changes increases long-term reliability.

Trade-off:
- Short-term friction for low-test changes.

## Gap Assessment

No high-value implementation gap identified for RFC 053 scope.

## Deviations and Evolution Since Original RFC

1. None material.

## Proposed Changes

1. Keep classification as `Fully implemented and aligned`.

## Test and Validation Evidence

1. `scripts/coverage_gate.py`

## Original Acceptance Criteria Alignment

Aligned.

## Rollout and Backward Compatibility

No runtime change introduced by this documentation retrofit.

## Open Questions

1. None for RFC 053 scope.

## Next Actions

1. Reassess threshold only with explicit data-backed governance decision.
