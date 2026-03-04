# RFC 053 - Enforce 99 Percent Query Service Coverage Gate

## Problem Statement
lotus-core query-service coverage is measured at 99%, but the enforced gate still allows 95%, which permits regression below platform quality expectations.

## Root Cause
`scripts/coverage_gate.py` was not updated after coverage hardening wave 2.

## Proposed Solution
Raise `FAIL_UNDER` in `scripts/coverage_gate.py` from `95` to `99`.

## Architectural Impact
No runtime or API impact. CI quality gate behavior is tightened.

## Risks and Trade-offs
- PRs with insufficient tests will fail faster.
- Minor increase in short-term remediation work for low-coverage changes.

## High-Level Implementation Approach
1. Update the fail-under threshold to 99.
2. Run `python scripts/coverage_gate.py`.
3. Merge and monitor CI.
