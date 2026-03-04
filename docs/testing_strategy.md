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
