# CR-861: Ingestion Pipeline Ruff Format Batch

Status: Hardened on 2026-06-02.

## Finding

After CR-860, Ruff lint was clean and enforced, but full `ruff format --check .` still reported 90
files requiring formatting. The next bounded subset covered ingestion DTO/router/settings files,
event-replay ingestion operations, pipeline-orchestrator consumers/repository, and closest focused
tests.

## Change

Ran Ruff formatting against selected files under:

1. `src/services/ingestion_service/`,
2. `src/services/event_replay_service/app/routers/ingestion_operations.py`,
3. `src/services/pipeline_orchestrator_service/`,
4. focused ingestion and pipeline-orchestrator tests.

The repository-wide format baseline is down from 90 files to 68 files requiring formatting.

## Boundary Preserved

This change does not alter:

1. ingestion DTO shape,
2. ingestion router behavior,
3. pipeline orchestration behavior,
4. event-replay ingestion operation behavior,
5. API contracts,
6. database schema or migration graph shape.

## Wiki Decision

No repo-local `wiki/` source update is included. This is mechanical formatting of runtime service
files and focused tests with no operator-facing behavior change.

## Validation

Local validation passed for the slice:

1. scoped `python -m ruff format --check <batch>`,
2. `make quality-ruff-gate`,
3. `python -m ruff format --check .` baseline measurement,
4. `python -m py_compile <batch>`,
5. focused ingestion/pipeline tests and collection checks,
6. `git diff --check`.
