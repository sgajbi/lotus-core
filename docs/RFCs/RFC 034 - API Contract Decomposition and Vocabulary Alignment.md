# RFC 034 - API Contract Decomposition and Vocabulary Alignment

- Date: 2026-02-23
- Services Affected: `query-service`, `lotus-gateway` (future)
- Status: Proposed

## Summary

This RFC addresses oversized API contracts and inconsistent domain wording by defining a decomposition path aligned to lotus-gateway-first delivery.

## Current Pain Points

1. `POST /portfolios/{id}/review` is broad and combines multiple bounded concerns.
2. Some DTOs still lack complete attribute-level descriptions/examples.
3. Mixed vocabulary appears across responses (`status`, `reprocessing_status`, `portfolio_type`, etc.) without canonical glossary linkage.

## Proposal

1. Keep `review` as an orchestrated convenience API.
2. Formalize smaller domain APIs as first-class lotus-gateway building blocks:
   - overview
   - holdings
   - performance
   - risk
   - activity
3. Enforce canonical vocabulary via shared schema package and lintable contract checks.
4. Require examples and descriptions for all external DTO fields.

## Decision Rationale

1. Preserves momentum for UI delivery while reducing long-term coupling.
2. Improves testability, performance tuning, and selective caching.
3. Reduces support burden by making each business concern independently observable.

## Rollout Plan

1. Phase 1: improve docs/examples for high-traffic DTOs.
2. Phase 2: publish decomposed endpoints and mark `review` as composed aggregate.
3. Phase 3: move composition policy to lotus-gateway as it matures.
