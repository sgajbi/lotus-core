RFC-050: Query Service Simulation Coverage Hardening Wave 1

Status: Implemented
Date: 2026-02-24
Owner: lotus-core Team

## Context

The lotus-core query-service coverage gate currently reports 94% and the lowest-covered modules are concentrated in simulation flows:

- `app/repositories/simulation_repository.py`
- `app/services/simulation_service.py`
- `app/routers/simulation.py`

These modules are central to sandbox proposal workflows consumed by lotus-gateway and need stronger regression protection.

## Problem Statement

Simulation coverage is insufficient across error paths and guard-rails:

- Session lifecycle validation and expired/inactive checks.
- Repository rollback path on missing delete target.
- Router-level HTTP status mapping for service exceptions.
- Projection edge cases (unknown instruments, non-positive projected quantity filtering).

This creates elevated regression risk for session state, projected positions, and policy-evaluation flows.

## Decision

Add a focused simulation test hardening wave:

1. Add dedicated unit tests for simulation repository behavior.
2. Expand simulation service tests for guard branches and projection variants.
3. Expand simulation router integration tests for error-to-HTTP mapping.
4. Ensure local test dependency completeness for test collection (`openpyxl` required by upload ingestion tests).

## Scope

In scope:

- lotus-core query-service tests and RFC documentation.
- Test dependency update in `tests/requirements.txt`.

Out of scope:

- Functional behavior changes to simulation business logic.
- API contract changes.

## Risks and Trade-offs

- Additional tests increase runtime moderately.
- Branch-focused tests increase coupling to current guard behavior, accepted for deterministic quality control.

## Validation

- `python scripts/coverage_gate.py`
- `python -m pytest tests/unit/services/query_service/services/test_simulation_service.py`
- `python -m pytest tests/integration/services/query_service/test_simulation_router_dependency.py`
- `python -m pytest tests/unit/services/query_service/repositories/test_simulation_repository.py`

## Follow-up

Wave 2 should target remaining lower-coverage query-service modules (integration, position, capabilities, and operations routers/services) to move lotus-core from 94% toward the platform 99% target.
