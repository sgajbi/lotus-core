# CR-333 Web Stack Framework Convergence

## Scope
Shared FastAPI/Uvicorn/Prometheus web stack across `lotus-core` services.

## Finding
`lotus-core` still carried two framework stacks across services:
- older services on `fastapi==0.111.0`, `uvicorn==0.30.1`, `prometheus-fastapi-instrumentator==7.0.0`
- newer services on `fastapi==0.129.0`, `uvicorn==0.35.0`, `prometheus-fastapi-instrumentator==7.1.0`

That kept a truthful repo-wide runtime lock out of reach even after the shared build constraints and wheel-based image work.

## Fix
- Converged all remaining services onto:
  - `fastapi==0.129.0`
  - `uvicorn==0.35.0` / `uvicorn[standard]==0.35.0`
  - `prometheus-fastapi-instrumentator==7.1.0`

## Evidence
- `python -m pytest tests/unit/services/ingestion_service tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py -q`
- `python -m pytest tests/unit/services/valuation_orchestrator_service tests/unit/services/persistence_service -q`
- `docker build -f src/services/persistence_service/Dockerfile -t lotus-core-persistence-service-buildcheck .`

## Follow-up
- With the web/runtime stack converged, a broader shared runtime lock is now materially more realistic than it was before this slice.
