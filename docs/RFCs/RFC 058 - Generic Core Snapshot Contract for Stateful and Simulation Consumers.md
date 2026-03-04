# RFC 058 - Generic Core Snapshot Contract for Stateful and Simulation Consumers

- Status: Proposed (refined draft for approval)
- Date: 2026-02-27
- Authors: lotus-core and downstream service owners
- Related: RFC 035, RFC 036, RFC 043, RFC 046A, RFC 049, RFC 057, lotus-platform RFC-0067

## Problem Statement

Downstream services (`lotus-risk`, `lotus-performance`, advisory/reporting consumers) need one deterministic, API-first contract to retrieve:

1. Baseline portfolio state at a declared business date.
2. Simulation-projected state from a lotus-core session.
3. Comparable baseline vs projected vs delta views without client-side stitching.

Today, consumers can compose this from `positions` and `simulation-sessions/*`, but that causes orchestration drift, naming drift, and inconsistent valuation/weight logic across apps.

## Goals

1. Provide one consumer-agnostic snapshot contract in lotus-core.
2. Support both stateful (baseline) and simulation use cases with the same vocabulary.
3. Make baseline/projected/delta directly comparable for risk/performance/advisory workflows.
4. Keep lotus-core as data/calculation backbone, not downstream analytics owner.
5. Enforce RFC-0067 governance: canonical naming, examples, type-safe schemas, no aliases.

## Non-Goals

1. Creating consumer-specific endpoints in lotus-core.
2. Implementing risk/performance/reporting analytics in lotus-core.
3. Returning presentation-specific report formats.

## Decision

Introduce a single integration endpoint:

- `POST /integration/portfolios/{portfolio_id}/core-snapshot`

This endpoint is:

1. Section-driven.
2. Simulation-aware.
3. Currency-context aware.
4. Deterministic for identical inputs.

## Why This Refinement

Compared to the initial RFC draft, this refinement adds:

1. Explicit `snapshot_mode` to avoid ambiguous behavior.
2. First-class `positions_delta` section for simulation impact use cases.
3. Strong valuation context (`as_of_date`, `pricing_basis`, `reporting_currency`) in response metadata.
4. Private-banking-safe numeric policy: monetary values as Decimal-compatible schema (`type: string`, `format: decimal` in OpenAPI), weights as decimal.
5. Stronger cross-app future fit for advisory suitability, mandate checks, and pre-trade impact.

## Contract (Normative)

### Endpoint

- `POST /integration/portfolios/{portfolio_id}/core-snapshot`

### Request

```json
{
  "as_of_date": "2026-02-27",
  "snapshot_mode": "SIMULATION",
  "reporting_currency": "USD",
  "sections": [
    "positions_baseline",
    "positions_projected",
    "positions_delta",
    "portfolio_totals",
    "instrument_enrichment"
  ],
  "simulation": {
    "session_id": "SIM_0001",
    "expected_version": 3
  },
  "options": {
    "include_zero_quantity_positions": false,
    "include_cash_positions": true,
    "position_basis": "market_value_base",
    "weight_basis": "total_market_value_base"
  }
}
```

### Required fields

1. Path: `portfolio_id`
2. Body: `as_of_date`
3. Body: `snapshot_mode` (`BASELINE` or `SIMULATION`)
4. Body: `sections` (non-empty enum array)

### Conditional fields

1. `simulation.session_id` is required when `snapshot_mode=SIMULATION`.
2. `simulation.expected_version` optional optimistic lock guard.

### Optional fields

1. `reporting_currency` (default: portfolio base currency)
2. `options.include_zero_quantity_positions` (default `false`)
3. `options.include_cash_positions` (default `true`)
4. `options.position_basis` (default `market_value_base`)
5. `options.weight_basis` (default `total_market_value_base`)

## Response (Normative)

```json
{
  "portfolio_id": "DEMO_DPM_EUR_001",
  "as_of_date": "2026-02-27",
  "snapshot_mode": "SIMULATION",
  "valuation_context": {
    "portfolio_currency": "EUR",
    "reporting_currency": "USD",
    "position_basis": "market_value_base",
    "weight_basis": "total_market_value_base"
  },
  "simulation": {
    "session_id": "SIM_0001",
    "version": 3,
    "baseline_as_of_date": "2026-02-27"
  },
  "sections": {
    "positions_baseline": [],
    "positions_projected": [],
    "positions_delta": [],
    "portfolio_totals": {}
  }
}
```

## Section Semantics (Normative)

### `positions_baseline`

Point-in-time state for `as_of_date` (current epoch).

Minimum fields per row:

1. `security_id`
2. `quantity`
3. `market_value_base` (or selected `position_basis` equivalent)
4. `weight`
5. `currency`

### `positions_projected`

Projected state after applying simulation session changes, same field semantics as baseline.

### `positions_delta`

Per-security comparability block between baseline and projected:

1. `security_id`
2. `baseline_quantity`
3. `projected_quantity`
4. `delta_quantity`
5. `baseline_market_value_base`
6. `projected_market_value_base`
7. `delta_market_value_base`
8. `delta_weight`

This section is required for future advisory/risk/performance impact workflows and avoids repeated client-side diff logic.

### `portfolio_totals`

Includes baseline and projected totals plus delta totals used for controls:

1. `baseline_total_market_value_base`
2. `projected_total_market_value_base`
3. `delta_total_market_value_base`

### `instrument_enrichment`

Canonical enrichment only (`isin`, `asset_class`, `sector`, `country_of_risk`, etc.), no analytics-derived attributes.

## Determinism and Consistency Requirements

1. Same request payload + same underlying data/session version => byte-equivalent semantic response.
2. `as_of_date` is always explicit, never implicit runtime date.
3. Simulation session must belong to `portfolio_id`.
4. Currency conversion must be auditable and reproducible.
5. Requested section unavailable => explicit failure (no silent omission).

## Error Contract

Lotus standard error envelope with `correlation_id`.

1. `400` invalid enum/options combinations.
2. `404` missing portfolio/session.
3. `409` session portfolio mismatch or `expected_version` mismatch.
4. `422` schema validation failures.
5. `500` unhandled service errors.

## Type and Precision Policy

1. Monetary and weight values follow Lotus precision policy and decimal-safe modeling.
2. API schemas must not use binary floating-point for monetary values.
3. Rounding behavior must align with platform rounding vectors and documented policy.

## Governance (RFC-0067)

Implementation PRs must include:

1. OpenAPI updates with complete metadata and realistic examples.
2. Vocabulary inventory updates in lotus-platform (no duplicates, no aliases, canonical terms only).
3. No legacy term reintroduction.
4. Gates passing: OpenAPI quality, vocabulary validation, no-alias guard, mypy/type checks.

## Downstream Fit

The contract must serve:

1. `lotus-risk` (stateful + simulation impact inputs)
2. `lotus-performance` (stateful normalization inputs)
3. Future advisory/reporting simulation comparators

Downstream services continue to own analytics outputs and presentation schemas.

## Implementation Plan

1. PR-1 Contract and DTOs
 - request/response DTOs and enums
 - OpenAPI examples and error models
 - section/schema validation
2. PR-2 Orchestration
 - baseline assembly from canonical positions/portfolio context
 - simulation-projected assembly from simulation session state
 - delta section generation and controls
3. PR-3 Governance
 - inventory regeneration and validation
 - no-alias checks and docs updates
4. PR-4 Integration validation
 - cross-consumer smoke tests (risk/performance style inputs)

## Acceptance Criteria

1. Deterministic baseline/simulation snapshots for same inputs.
2. No consumer-specific endpoint fork in lotus-core.
3. Delta comparability available without client-side stitching.
4. RFC-0067 governance passes with updated inventory.
5. At least one non-risk consumer flow validated on same contract.

## Decision Points for Approval

1. Confirm `snapshot_mode` enum (`BASELINE`, `SIMULATION`) and optional future extension (`REPLAY` reserved).
2. Confirm `positions_delta` as mandatory section for `SIMULATION` mode.
3. Confirm decimal-safe API modeling policy for monetary and weight fields.
