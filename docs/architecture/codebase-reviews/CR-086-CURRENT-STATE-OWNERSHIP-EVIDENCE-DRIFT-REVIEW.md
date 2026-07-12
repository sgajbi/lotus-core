# CR-086 Current-State Ownership Evidence Drift Review

## Scope
- `docs/standards/durability-consistency.md`
- `docs/RFCs/RFC-INDEX.md`

## Finding
Two current-state documentation surfaces still used `app/main.py` as ownership evidence for control-plane behavior:

- `durability-consistency.md`
- `RFC-INDEX.md` (RFC-081 evidence row)

That is too weak for engineering traceability. The correct evidence for control-plane ownership is the actual router/service surface, not the app assembly entrypoint.

## Change
Replaced the weak evidence references with the live ownership paths:

- `src/services/query_control_plane_service/app/routers/integration.py`
- `src/services/query_control_plane_service/app/routers/operations.py`
- `src/services/query_control_plane_service/app/routers/simulation.py`
- `src/services/query_control_plane_service/app/routers/analytics_inputs.py`
- `src/services/query_control_plane_service/app/routers/capabilities.py`
- plus the real reconciliation and replay router paths where RFC-081 evidence was previously pointing only to service mains

## Why this is the right fix
- current-state docs now point to the code that actually implements the documented behavior
- ownership tracing is stronger for future reviews
- no runtime behavior changed

## Residual follow-up
- Continue the same rule whenever an RFC index or standard cites implementation evidence: prefer the concrete owning module over a generic `main.py` unless the startup contract itself is the subject.

## Evidence
- `docs/standards/durability-consistency.md`
- `docs/RFCs/RFC-INDEX.md`
