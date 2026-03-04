# RFC 056 - Remove Legacy Query Analytics and Reporting Endpoints

## Problem Statement
lotus-core query-service still exposes deprecated advanced analytics and reporting-style endpoints that are no longer aligned to target service ownership:
- advanced analytics belongs to lotus-performance
- reporting/aggregation belongs to lotus-report

## Root Cause
- Endpoints were marked `deprecated` but kept active to ease transition.
- Runtime behavior still executes local lotus-core analytics/reporting logic for these routes.

## Proposed Solution
Hard-disable legacy lotus-core query-service endpoints by returning `410 Gone` with explicit migration targets:
- `POST /portfolios/{portfolio_id}/performance` -> lotus-performance
- `POST /portfolios/{portfolio_id}/performance/mwr` -> lotus-performance
- `POST /portfolios/{portfolio_id}/risk` -> lotus-performance
- `POST /portfolios/{portfolio_id}/concentration` -> lotus-performance
- `POST /portfolios/{portfolio_id}/summary` -> lotus-report
- `POST /portfolios/{portfolio_id}/review` -> lotus-report

## Architectural Impact
- Enforces service boundaries at runtime, not only in documentation.
- Prevents duplicate analytics/reporting logic drift in lotus-core.
- Strengthens API-driven integration toward lotus-performance and lotus-report.

## Risks and Trade-offs
- Existing internal tests or scripts calling these routes must migrate immediately.
- Temporary disruption for local consumers not yet switched to lotus-performance/lotus-report.

Mitigations:
- Clear `410` error messages with target endpoints.
- Contract/integration test updates in this RFC scope.

## High-Level Implementation Approach
1. Update affected routers to return deterministic `410 Gone` responses.
2. Keep route surfaces temporarily for explicit migration signaling.
3. Update integration/e2e tests to assert `410` behavior.
4. Update runbook/docs to point to lotus-performance/lotus-report authoritative routes.

## Success Criteria
- Legacy lotus-core analytics/reporting routes no longer perform calculations.
- All affected tests and docs align to migration messaging.
- lotus-core runtime only serves core data and integration contracts.
