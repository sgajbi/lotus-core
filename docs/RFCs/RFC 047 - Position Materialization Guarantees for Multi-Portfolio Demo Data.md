# RFC 047 - Position Materialization Guarantees for Multi-Portfolio Demo Data

- Status: Implemented
- Date: 2026-02-24
- Authors: lotus-core Engineering
- Related:
  - `docs/RFCs/RFC 046 - Automated Demo Data Pack Bootstrap for End-to-End Platform Validation.md`

## 1. Problem Statement

During automated demo data bootstrap verification, lotus-core successfully persisted transactions for all demo portfolios, but only a subset produced open positions through `GET /portfolios/{portfolio_id}/positions`.

Observed example:

- `DEMO_DPM_EUR_001`: transactions available (`total=7`), review endpoint responsive, positions empty.

This weakens confidence in end-to-end position/valuation readiness for non-cash assets.

## 2. Root Cause (Current Understanding)

Likely causes include one or more of:

1. position calculation ordering/epoch behavior for mixed transaction sequences,
2. valuation gating causing non-cash snapshots to remain absent from latest-position views,
3. data-contract assumptions in query-service repositories that filter out expected rows.

Further root-cause analysis is required in position calculator, valuation calculator, and query repository flow.

## 3. Proposed Solution

1. Define explicit invariants for latest positions:
   - if net quantity > 0 for a portfolio-security key, the key must appear in latest positions.
2. Add integration test scenarios using deterministic multi-portfolio demo payloads.
3. Add support diagnostics endpoint metadata or logs identifying why a key is excluded.
4. Harden query repository filtering to avoid silently dropping valid open positions.

## 4. Architectural Impact

1. Improves lotus-core reliability as canonical holdings source for lotus-gateway/UI and downstream lotus-performance/lotus-manage.
2. Increases trust in demo bootstrap as a valid readiness signal.
3. Reduces false confidence from transaction-only success without holdings materialization.

## 5. Risks and Trade-offs

1. Fix may touch core position/valuation/query logic and require careful regression testing.
2. Stricter invariants may surface latent data quality defects previously hidden.

## 6. High-Level Implementation Approach

1. Capture failing portfolio-security keys from current demo run.
2. Trace state across:
   - transaction persistence,
   - position_state/daily_position_snapshots,
   - valuation status transitions,
   - query latest-position selection.
3. Implement logic fixes with unit + integration coverage.
4. Promote demo-data verification gate to require positions for all demo portfolios after fix.
