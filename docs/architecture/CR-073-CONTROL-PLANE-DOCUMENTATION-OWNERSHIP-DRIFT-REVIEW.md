# CR-073 Control-Plane Documentation Ownership Drift Review

## Scope
Clean current-state RFC and ADR references that still pointed to deleted `query_service` control-plane router paths after the RFC 81 ownership split.

## Findings
- A meaningful set of active RFCs and ADRs still referenced:
  - `src/services/query_service/app/routers/analytics_inputs.py`
  - `src/services/query_service/app/routers/capabilities.py`
  - `src/services/query_service/app/routers/integration.py`
  - `src/services/query_service/app/routers/operations.py`
  - `src/services/query_service/app/routers/simulation.py`
- Those paths are no longer current-state implementation. The live ownership now sits under `query_control_plane_service`.
- Review artifacts such as `CR-009` intentionally still mention the old paths as migration evidence and should not be rewritten.

## Changes
1. Rewrote current-state RFC and ADR references from the deleted `query_service` control-plane router paths to the live `query_control_plane_service` paths.
2. Corrected the stale source-path header comment at the top of:
   - `src/services/query_control_plane_service/app/routers/simulation.py`
3. Left review-history artifacts unchanged where they intentionally describe pre-refactor state.

## Validation
- `rg -n "src/services/query_service/app/routers/(analytics_inputs|capabilities|integration|operations|simulation)\.py" docs/RFCs docs/architecture`
- Remaining hits are limited to:
  - `docs/architecture/CR-009-QUERY-CONTROL-PLANE-OWNERSHIP-REVIEW.md`

## Residual Risk
- Historical RFCs that are intentionally archival may still mention older ownership if they are documenting prior state rather than current implementation. That is acceptable as long as current-state ADRs and active RFCs point to the live source tree.
