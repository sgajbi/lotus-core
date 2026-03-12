# RFC 062 - Reference Series Integration Contract for Benchmark and Risk-Free Data

| Field | Value |
| --- | --- |
| Status | Implemented |
| Created | 2026-03-01 |
| Last Updated | 2026-03-04 |
| Owners | lotus-core query + ingestion owners; downstream lotus-performance consumers |
| Depends On | RFC 049, RFC 057, RFC 058, RFC-0067 |
| Related Standards | `docs/standards/api-vocabulary/lotus-core-api-vocabulary.v1.json`; API-first ops standards |
| Scope | Cross-repo |

## Executive Summary
RFC 062 establishes lotus-core as canonical provider of benchmark assignment/definition/reference series inputs and ingestion contracts, while lotus-performance owns derived analytics.

Core query contracts, ingestion contracts, and reference-data coverage endpoints are implemented and test-covered. This RFC is largely aligned with current runtime behavior.

## Original Requested Requirements (Preserved)
1. Deterministic benchmark assignment resolution.
2. Benchmark/index master and raw series query contracts.
3. Risk-free series query contracts with explicit conventions.
4. Matching ingestion contracts for assignments, definitions, compositions, index/benchmark/risk-free series.
5. Operational coverage endpoints for benchmark/risk-free data quality and availability.
6. Strict ownership split: lotus-core provides raw data, lotus-performance performs analytics.

## Current Implementation Reality
1. Query integration endpoints for benchmark assignment/definition/catalog/series/coverage and risk-free series/coverage exist.
2. Ingestion reference-data endpoints exist for benchmark/index/risk-free datasets and classification taxonomy.
3. Integration router and unit tests cover primary request/response and error paths.
4. OpenAPI vocabulary inventory includes these routes and canonical terms.

## Requirement-to-Implementation Traceability
| Requirement | Current State | Evidence |
| --- | --- | --- |
| Benchmark assignment + definition query contracts | Implemented | `src/services/query_control_plane_service/app/routers/integration.py`; `tests/unit/services/query_service/routers/test_integration_router.py` |
| Benchmark/index catalog + series query contracts | Implemented | same integration router + integration router unit tests |
| Risk-free query + coverage contracts | Implemented | `integration.py` (`/reference/risk-free-series`, `/reference/risk-free-series/coverage`) |
| Reference ingestion endpoints | Implemented | `src/services/ingestion_service/app/routers/reference_data.py` |
| Coverage diagnostics endpoints | Implemented | `integration.py` coverage routes + service/tests |
| Vocabulary/OpenAPI governance | Implemented | `docs/standards/api-vocabulary/lotus-core-api-vocabulary.v1.json` |

## Design Reasoning and Trade-offs
1. Centralizing reference-data query contracts in lotus-core avoids cross-app drift in assignment and convention handling.
2. Keeping only raw/reference outputs in lotus-core preserves ownership boundaries and avoids analytics duplication.
3. Trade-off: downstream services must orchestrate analytics transformations, but this is intentional architecture.

## Gap Assessment
1. No major runtime contract gap found for RFC-062 core ask.
2. Continuous cross-app contract validation remains required as downstream consumers evolve.

## Deviations and Evolution Since Original RFC
1. RFC title in file and heading had naming drift; this standardized version keeps consistent naming and governance framing.
2. Endpoint family includes classification taxonomy contract extension beyond the earliest baseline ask, aligned with attribution needs.

## Proposed Changes
1. Keep RFC 062 as implemented and aligned baseline.
2. Maintain contract regression tests and vocabulary sync in CI for future schema changes.

## Test and Validation Evidence
1. `src/services/query_control_plane_service/app/routers/integration.py`
2. `tests/unit/services/query_service/routers/test_integration_router.py`
3. `src/services/ingestion_service/app/routers/reference_data.py`
4. `docs/standards/api-vocabulary/lotus-core-api-vocabulary.v1.json`

## Original Acceptance Criteria Alignment
1. Query and ingestion contracts for benchmark/risk-free references: aligned.
2. Ownership boundary (raw vs derived analytics): aligned.
3. Deterministic and ops-supportable contract surface: aligned.

## Rollout and Backward Compatibility
1. Contracts are additive and integration-focused.
2. Downstream consumers should continue using query-service integration routes, not DB coupling.

## Open Questions
1. Should cross-repo contract suites include stricter consumer-side schema lock tests for lotus-performance and lotus-risk in one shared automation pipeline?

## Next Actions
1. Continue cross-repo contract smoke checks against downstream apps.
2. Keep RFC-0067 governance gates mandatory for any new reference-series fields.
