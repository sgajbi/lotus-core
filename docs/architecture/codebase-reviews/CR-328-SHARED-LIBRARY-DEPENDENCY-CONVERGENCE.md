# CR-328 Shared Library Dependency Convergence

## Scope
Python dependency alignment between `portfolio-common` and service package metadata used in Docker image builds.

## Finding
Real image builds showed that multiple services were installing versions of `pydantic`, `sqlalchemy`, `asyncpg`, and `confluent-kafka` that downgraded the already-installed `portfolio-common` dependency set inside the same image. The builds still succeeded, but only with explicit resolver conflict warnings.

This was a real build-governance defect:
- image contents were internally inconsistent
- shared-library assumptions could drift from runtime reality
- “green build” did not mean coherent dependency state

## Fix
- Aligned all service `pyproject.toml` files with `portfolio-common` for the overlapping shared runtime dependencies:
  - `pydantic==2.12.5`
  - `sqlalchemy==2.0.46`
  - `asyncpg==0.30.0`
  - `confluent-kafka==2.12.0` where applicable

## Evidence
- `docker build -f src/services/query_service/Dockerfile -t lotus-core-query-service-buildcheck .`
- `docker build -f src/services/valuation_orchestrator_service/Dockerfile -t lotus-core-valuation-orchestrator-buildcheck .`

Both builds completed without the previous resolver-conflict warnings.

## Follow-up
- Move from version convergence to proper locked dependency artifacts for image and CI builds.
- Consider centralizing shared dependency pins to reduce future service metadata drift.
