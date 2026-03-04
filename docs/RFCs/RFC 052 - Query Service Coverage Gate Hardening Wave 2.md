# RFC 052 - Query Service Coverage Gate Hardening Wave 2

## Problem Statement
lotus-core query-service combined `unit + integration-lite` coverage was below the platform target and key policy/governance branches were untested, which increased regression risk for integration contracts.

## Root Cause
Coverage emphasis was skewed toward happy-path service tests. Several branch paths in integration policy resolution, capabilities override normalization, and app lifecycle logging were not exercised by the enforced coverage gate suite.

## Proposed Solution
1. Add focused tests for lotus-core integration policy branch behavior (tenant defaults, strict-mode provenance, lotus-performance-owned analytics delegation, stale freshness path, attribute/key fallback behavior).
2. Add focused tests for capabilities policy JSON normalization and override edge cases.
3. Add lifespan logging test for query-service startup/shutdown behavior.
4. Include capabilities router dependency test in `coverage_gate.py` integration-lite list.

## Architectural Impact
No runtime API contract changes. This is a verification and quality hardening increment for lotus-core query-service policy/control-plane behavior.

## Risks and Trade-offs
- Low runtime risk (test-only changes + coverage gate input expansion).
- Slight increase in CI runtime for lotus-core query-service gate.

## High-Level Implementation Approach
1. Extend unit tests under `tests/unit/services/query_service/services` and `tests/unit/services/query_service/repositories`.
2. Extend integration-lite tests under `tests/integration/services/query_service`.
3. Update `scripts/coverage_gate.py` to include capabilities router test.
4. Validate with `python scripts/coverage_gate.py` and ensure combined coverage >= 99%.
