# RFC 068 - Active Query DTO Pyramid Hardening

| Field | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-03-05 |
| Last Updated | 2026-03-05 |
| Owners | lotus-core query-service maintainers |
| Depends On | RFC 057, RFC 063, RFC 067 |
| Scope | DTO contract-pyramid hardening for active query-service domains |

## Executive Summary
This RFC supersedes RFC-055’s legacy-domain DTO scope. It defines the DTO pyramid
for active query-service contracts and the required unit-level contract checks.

## Active DTO Domains
1. Integration DTOs (including policy and benchmark/risk-free reference contracts)
2. Core snapshot DTOs
3. Analytics input DTOs
4. Foundational query DTOs (portfolio, transaction, position, instrument, market data)
5. Wealth reporting DTOs
6. Simulation DTOs
7. Lookup/catalog DTOs
8. Operations support/lineage DTOs

## DTO Pyramid Rules
1. DTO unit tests must cover required/optional fields and enum/domain constraints.
2. Request/response examples must align with actual field names and data types.
3. New DTOs require at least one direct unit test module in `tests/unit/services/query_service/dtos`.
4. Breaking schema changes require explicit RFC/backward-compatibility note.
5. DTOs that carry currency-translated amounts must document native, portfolio, and reporting currency semantics explicitly.

## Required Evidence and Tests
1. `tests/unit/services/query_service/dtos/test_core_snapshot_dto.py`
2. `tests/unit/services/query_service/dtos/test_analytics_input_dto.py`
3. `tests/unit/services/query_service/dtos/test_lookup_dto.py`
4. `tests/unit/services/query_service/dtos/test_reporting_dto.py`
5. `tests/unit/services/query_service/services/test_integration_service.py`
6. `tests/unit/services/query_service/services/test_simulation_service.py`

## Success Criteria
1. Active DTO domains are explicitly covered by unit-level contract tests.
2. No test dependency remains on legacy review/performance/MWR DTO families.
3. DTO governance remains aligned with OpenAPI and vocabulary gates in CI.
