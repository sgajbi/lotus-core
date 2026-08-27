# Incident To Coverage Traceability

## Purpose

This document maps production and pre-production incident classes to deterministic
test coverage expectations, so every failure mode has an explicit prevention or
detection layer in lotus-core.

## Mapping

| Incident Class | Failure Pattern | Expected Coverage Layer | Primary Evidence Paths |
| --- | --- | --- | --- |
| Schema drift / contract mismatch | Consumer payload no longer matches event model | Unit + consumer-boundary integration | `tests/unit/transaction_specs`; `tests/integration/services/persistence_service/consumers` |
| Idempotency regression | Duplicate message replays persist duplicate artifacts | Consumer-boundary integration + integration repository tests | `tests/integration/services/persistence_service/consumers`; `tests/integration/services/persistence_service/repositories` |
| Query pagination inconsistency | Page token reused across different request scope | Unit service tests | `tests/unit/services/query_control_plane_service/application/analytics/test_analytics_timeseries_service.py` |
| Snapshot epoch race / drift | Composite query pages observe mixed epochs | Unit service + repository tests | `tests/unit/services/query_control_plane_service/application/analytics/test_analytics_timeseries_service.py`; `tests/unit/services/query_control_plane_service/infrastructure/test_analytics_timeseries_repository.py` |
| Policy-governance bypass | Disallowed snapshot sections exposed under strict policy | Router/service unit + OpenAPI integration | `tests/integration/services/query_control_plane_service/test_integration_router_dependency.py`; `tests/integration/services/query_service/test_main_app.py` |
| Replay/reprocessing atomicity break | Partial persistence when downstream publish fails | Transaction-processing integration tests | `tests/integration/services/portfolio_transaction_processing_service/test_int_position_reprocessing_atomicity.py` |
| Demo/bootstrap data drift | Demo pack schema or expected holdings diverge from contract | Integration tooling tests | `tests/integration/tools/test_demo_data_pack.py` |

## Policy

1. Every Sev-1/Sev-2 incident requires either:
   1. a new deterministic test, or
   2. an explicit rationale why a test is not the correct control.
2. New RFC deltas that touch reliability/correctness must update this map.
3. The mapping is append-oriented: do not remove incident classes without a supersession note.
