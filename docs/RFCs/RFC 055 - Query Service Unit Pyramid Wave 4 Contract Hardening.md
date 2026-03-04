# RFC 055 - Query Service Unit Pyramid Wave 4 Contract Hardening

## Problem Statement
lotus-core query-service satisfies coverage gates but remains below platform unit-test ratio targets in the overall lotus-core pyramid.

## Root Cause
- Unit test volume is still light relative to integration and e2e counts.
- Several DTO/API contract branches are insufficiently stress-tested.

## Proposed Solution
Add a high-signal, unit-heavy contract validation suite for query-service DTOs:
- performance request/response contracts
- MWR request contracts
- review response alias and section contracts
- position analytics request/response alias and enum contracts

## Architectural Impact
No runtime behavior changes. This increment improves confidence in API contracts and raises unit-test pyramid depth.

## Risks and Trade-offs
- Longer unit suite runtime in CI.
- No production regression risk expected as service logic is unchanged.

## High-Level Implementation Approach
1. Add a dedicated unit test module focused on DTO contract invariants and edge validation.
2. Run local query-service quality gates (`ruff`, targeted `pytest`, `coverage_gate.py`).
3. Raise PR and monitor CI to merge cleanly.
