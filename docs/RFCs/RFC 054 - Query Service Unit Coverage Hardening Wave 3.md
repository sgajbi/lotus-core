# RFC 054 - Query Service Unit Coverage Hardening Wave 3

## Problem Statement
lotus-core query-service currently meets the 99% combined coverage gate, but several branch paths in unit scope are still underrepresented and reduce confidence in service-level behavior.

## Root Cause
- Unit tests do not fully cover selected edge paths in `performance_service`, `simulation_service`, and `integration_service`.
- `lookup_dto` contract models are not directly unit tested.

## Proposed Solution
Add a focused unit test wave for high-signal branch and contract paths:
- `PerformanceService`: empty period list and DAILY breakdown attributes branch behavior.
- `SimulationService`: successful `get_session` and `add_changes` orchestration paths.
- `IntegrationService`: `get_effective_policy` branch when `include_sections` is omitted but policy already resolves allowed sections.
- `lookup_dto`: model validation and default factory behavior.

## Architectural Impact
No runtime/API contract changes. This is a quality-hardening increment that improves confidence in existing behavior.

## Risks and Trade-offs
- Slightly longer unit test execution time.
- No functional risk expected because production code is unchanged.

## High-Level Implementation Approach
1. Add/extend unit tests in existing query-service unit suites.
2. Execute lotus-core query-service coverage gate workflow equivalent locally.
3. Keep CI and documentation aligned with this test-wave increment.
