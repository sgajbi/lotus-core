# CR-016 Pure HTTP Bootstrap Review

## Scope

Pure HTTP/control-plane app bootstrap in:

- `query_service`
- `query_control_plane_service`
- `event_replay_service`
- `financial_reconciliation_service`
- `ingestion_service`

## Findings

These services repeat a large shared bootstrap pattern:

- FastAPI app construction
- Prometheus `/metrics` exposure
- OpenAPI generation with metrics content override and schema enrichment
- correlation/request/trace header middleware
- HTTP observability middleware
- unhandled exception normalization
- health router inclusion

This is a real maintainability seam, not just superficial similarity.

The duplication is already carrying some cost:

- the same correlation/observability/exception behavior is maintained in
  multiple apps
- review and hardening work must be repeated app by app
- future drift risk is high

## Why this was not refactored in the current slice

This bootstrap layer is more sensitive than the worker `main.py` convergence:

- enterprise middleware differs between some apps
- dependency-critical startup behavior differs (`ingestion_service` is
  intentionally fail-fast on Kafka producer init)
- health dependency sets differ (`db`, `kafka`, or both)

So while the duplication is real, the correct fix is not a quick mechanical
helper. It needs a deliberate app-bootstrap design that preserves service-local
contracts while extracting the genuinely shared middleware and OpenAPI wiring.

## Recommended next step

Design a shared HTTP bootstrap utility with explicit hooks for:

- service name and prefix
- app title/description/version
- enterprise middleware inclusion
- startup dependency policy
- health dependency set
- router registration

That should be handled as its own convergence batch, not folded casually into
the current runtime review.

## Evidence

- `src/services/query_service/app/main.py`
- `src/services/query_control_plane_service/app/main.py`
- `src/services/event_replay_service/app/main.py`
- `src/services/financial_reconciliation_service/app/main.py`
- `src/services/ingestion_service/app/main.py`
