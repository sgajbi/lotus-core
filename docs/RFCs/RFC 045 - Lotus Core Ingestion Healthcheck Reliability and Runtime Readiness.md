# RFC 045 - lotus-core Ingestion Healthcheck Reliability and Runtime Readiness

- Status: IMPLEMENTED
- Date: 2026-02-24
- Owners: lotus-core Ingestion Service

## Problem Statement

In local Docker startup, `ingestion_service` remains `unhealthy` even when ingestion API calls and `/health/ready` respond successfully.
This creates false-negative platform health signals and weakens operational confidence for integration testing and orchestration.

## Root Cause

The container healthcheck command depends on `curl`, but the ingestion image does not include `curl`.
Docker health probes fail with `/bin/sh: 1: curl: not found`, producing persistent `unhealthy` state despite service readiness.

## Proposed Solution

1. Replace the ingestion healthcheck command with a probe that does not rely on missing OS tools.
2. Standardize healthchecks across lotus-core services to use one of:
   - `python -c` HTTP probe, or
   - a lightweight binary guaranteed in image baseline.
3. Add CI/container smoke validation to assert healthcheck tooling availability and healthy status after startup.

## Architectural Impact

- Improves container-level observability fidelity for lotus-core and downstream platform stacks.
- Reduces false alarms in local and CI compose workflows.
- Aligns health semantics with platform reliability expectations.

## Risks and Trade-offs

- Updating probe strategy can mask regressions if probe endpoint itself is too shallow.
- Standardized probe behavior may require Dockerfile adjustments across multiple lotus-core services.
- Slight increase in CI runtime for healthcheck validation gates.

## High-Level Implementation Approach

1. Update ingestion container healthcheck in compose/docker artifacts to a guaranteed-available probe command.
2. Verify probe endpoint coverage (`/health/ready` vs `/health/live`) aligns with orchestration expectations.
3. Add compose smoke assertion that fails if service reports `unhealthy` after warm-up.
4. Document healthcheck policy in lotus-core runbook/developer docs.
