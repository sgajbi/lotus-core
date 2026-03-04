# RFC 046A - lotus-core Simulation Session Contract for Proposal Sandbox

## Problem Statement
lotus-core currently supports ingestion/query flows for actual portfolio data but lacks a first-class session model for iterative proposal simulation. UI/lotus-gateway cannot persist and recalculate tentative proposal changes safely and repeatedly.

## Root Cause
- No lotus-core API contract for simulation session lifecycle.
- No session-scoped transaction ledger separate from committed portfolio transactions.
- No canonical projected holdings endpoint based on simulated changes.

## Proposed Solution
Introduce lotus-core simulation session capabilities with explicit lifecycle and projection APIs.

### 1. Session Lifecycle APIs
- `POST /simulation-sessions`
  - input: `portfolio_id`, optional metadata
  - output: `session_id`, `status`, `expires_at`, `version`
- `GET /simulation-sessions/{session_id}`
- `DELETE /simulation-sessions/{session_id}` (or close/archive)

### 2. Session Change APIs
- `POST /simulation-sessions/{session_id}/changes`
  - upsert one or more change intents (`BUY`, `SELL`, `DEPOSIT`, `WITHDRAWAL`, etc.)
  - returns new `version`
- `DELETE /simulation-sessions/{session_id}/changes/{change_id}`

### 3. Session Projection APIs
- `GET /simulation-sessions/{session_id}/projected-positions`
- `GET /simulation-sessions/{session_id}/projected-summary`

Projection merges:
- current portfolio baseline snapshot
- ordered session changes
- existing lotus-core valuation/FX references (where available)

## Architectural Impact
- Adds a product-layer simulation context in lotus-core without mutating committed transactions.
- Creates a clean handoff contract to lotus-performance and lotus-manage for delta analytics and policy evaluation.
- Enables lotus-gateway to orchestrate iterative workflows safely with session/version controls.

## Data and Governance Principles
- Session data is non-booking, non-execution state.
- Session must be tenant and user scoped.
- Session operations require optimistic concurrency (`version`).
- Session TTL and cleanup policy required.

## Risks and Trade-offs
- Increased API/state surface in lotus-core.
- Risk of stale sessions without cleanup.
- Potential confusion between simulated and committed states.

## Mitigations
- Distinct namespaces (`simulation-sessions/*`).
- Mandatory explicit `session_id` in all simulation calls.
- TTL + background cleanup job.
- Clear response metadata: `is_simulated=true`, `baseline_as_of`.

## High-Level Implementation Approach
1. Add schema/tables for sessions + session changes.
2. Add service layer for lifecycle, change validation, and projection builder.
3. Expose query APIs for projected positions/summary.
4. Add contract tests and integration tests with demo portfolios.
5. Add lotus-gateway consumer examples and operational diagnostics.

## Success Criteria
- UI/lotus-gateway can create a session, post iterative changes, and retrieve projected positions deterministically.
- No writes to committed transaction tables from simulation APIs.
- Session APIs are observable and covered by integration tests.
