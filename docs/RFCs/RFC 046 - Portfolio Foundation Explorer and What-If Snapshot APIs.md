# RFC 046 - Portfolio Foundation Explorer and What-If Snapshot APIs

- Status: PROPOSED
- Date: 2026-02-24
- Owners: lotus-core Query Service

## Problem Statement

A domain-grade portfolio foundation experience requires low-latency access to current portfolio state, composition, and health metrics, plus fast what-if snapshots for iterative advisory and lotus-manage workflows.

## Root Cause

- Existing lotus-core APIs are oriented to point features and supportability surfaces.
- No explicit query surface optimized for portfolio explorer + iterative editing workflows.
- What-if state projection is not formalized as a first-class contract.

## Proposed Solution

1. Portfolio Foundation Explorer APIs
   - Portfolio list/detail read models with positions, transactions summary, composition and health indicators.
2. What-If Snapshot APIs
   - Accept portfolio reference + staged deltas and return projected holdings/weights/exposures summary for UI iteration loops.
3. Consistent provenance and freshness metadata
   - Ensure each response includes timestamp/provenance to support trustable frontend decisions.

## Architectural Impact

- Strengthens lotus-core role as portfolio data foundation for all product journeys.
- Enables lotus-gateway lifecycle orchestration with stable, simulation-ready contracts.
- Requires performance-focused query paths and response shaping.

## Risks and Trade-offs

- Additional query complexity and caching strategy requirements.
- Potential confusion between persistent ingestion and ephemeral what-if contracts if not clearly separated.
- Requires strict governance around section ownership and derived metrics boundaries.

## High-Level Implementation Approach

1. Define explorer schema and pagination/filter model.
2. Define what-if delta schema and projection response model.
3. Add contract tests and latency budgets for UI interaction loops.
4. Roll out behind feature flags for staged UI adoption.

## Dependencies

- Consumed by lotus-gateway RFC-0010 and AW RFC-0007.
- lotus-performance and lotus-manage contracts integrate with what-if projection outputs.
