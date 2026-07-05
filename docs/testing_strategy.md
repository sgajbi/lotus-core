# Lotus-Core Testing Strategy

## Purpose

This document defines the repository-wide testing architecture used to keep lotus-core production-safe while enabling fast feedback.

## Test Layers

1. Unit tests (`tests/unit`)
   1. Validate deterministic domain logic, DTO contracts, and service-level error mapping.
   2. Must prefer real domain models (Pydantic events/DTOs) over ad-hoc dict mocks.
2. Integration tests (`tests/integration`)
   1. Validate service-boundary behavior with realistic persistence and router wiring.
   2. Cover supportability, lineage, snapshot, and policy-governed contracts.
3. End-to-end tests (`tests/e2e`)
   1. Validate multi-service workflows and externalized behavior.
   2. Used for release confidence, not for inner-loop iteration.

## Consumer-Boundary Pattern

Use a focused consume-process-persist test pattern to bridge unit and full E2E:
1. Prepare event payload using canonical event models.
2. Execute consumer processing path.
3. Assert persistence side effects (state tables, jobs, outbox/idempotency where applicable).
4. Assert error class mapping for retryable vs non-retryable failures.

## Contract and Governance Coverage

1. OpenAPI contract assertions must verify required response/error contracts.
2. Integration policy behavior must be tested in both strict and non-strict modes.
3. Snapshot and analytics APIs must include deterministic pagination and lineage metadata behavior.
4. Critical domains and proof families are governed by
   `docs/standards/risk-based-test-coverage-matrix.v1.json`.
5. Run `make risk-based-test-coverage-matrix-guard` after adding or changing high-risk behavior,
   test suites, proof-family markers, or CI lane ownership.

## Proof-Family Markers

The repository keeps `--strict-markers` enabled. Use proof-family markers when they clarify the
primary evidence type for a test module or case:

1. `api` for HTTP request, response, pagination, or problem-details contracts.
2. `contract` for schema, event, OpenAPI, source-data, or governance contracts.
3. `middleware` for HTTP middleware, auth, audit, header, or diagnostics behavior.
4. `security` for authorization, privacy, secrets, or abuse-boundary controls.
5. `regression` for golden scenarios or previously fixed defects.
6. `e2e` for multi-service end-to-end workflows.

Do not use marker count as proof. The risk matrix must cite concrete tests or Make targets and must
record `partial`, `missing`, or `deliberately_deferred` with a follow-up issue when evidence is not
complete.

## CI Execution Guidance

1. Pull request:
   1. Run fast unit + targeted integration suites.
2. Main and nightly:
   1. Run expanded integration + E2E + heavy diagnostics suites.
3. New feature slices must include:
   1. Unit coverage for logic branches.
   2. At least one boundary/integration assertion for external behavior.

## Quality Gates

1. No new endpoint without explicit success + error contract tests.
2. No new pagination token logic without tamper/scope validation tests.
3. No governance/policy change without strict-mode and non-strict-mode assertions.
4. No high-risk behavior change without updating or confirming the risk-based test coverage matrix.
