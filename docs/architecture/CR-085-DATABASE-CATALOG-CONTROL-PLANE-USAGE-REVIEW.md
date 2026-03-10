# CR-085 Database Catalog Control-Plane Usage Review

## Scope
- `docs/Database-Schema-Catalog.md`

## Finding
The database schema catalog still listed `src/services/query_control_plane_service/app/main.py` as a table-usage reference in several places.

That was technically true but practically weak. `main.py` is only the app assembly layer. It does not tell engineers which control-plane router or service actually owns the table access pattern.

The affected areas were:

- simulation session/change tables
- benchmark and reference-data tables
- analytics export job table

## Change
Replaced `query_control_plane_service/app/main.py` references with the actual ownership paths:

- `src/services/query_control_plane_service/app/routers/simulation.py`
- `src/services/query_control_plane_service/app/routers/integration.py`
- `src/services/query_control_plane_service/app/routers/analytics_inputs.py`

## Why this is the right fix
- the catalog is now more useful for code review and ownership tracing
- current-state documentation points to real business/API ownership rather than app bootstrapping
- no runtime behavior changed

## Residual follow-up
- Continue the same rule for future schema catalog maintenance: reference the owning repository/service/router path, not just the app entrypoint.

## Evidence
- `docs/Database-Schema-Catalog.md`
