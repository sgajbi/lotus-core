# CR-1345 Health Runtime Metadata

Date: 2026-07-05

## Objective

Locally fix GitHub issue #564 by adding safe deployment and build metadata to shared health and
readiness responses without weakening liveness/readiness semantics.

## Finding

`/health/live` and `/health/ready` exposed process and dependency state but did not include service
identity, app version, environment/profile, started-at/uptime, or build/revision metadata. Operators
could use `GET /version`, but incident triage often starts from health probes and should not require
shell access or log scraping to correlate a running service to an image release.

## Changes

1. Added `HealthRuntimeMetadata` to `portfolio_common.health`.
2. Extended liveness and readiness payloads with a bounded `runtime` block containing service name,
   app version, environment, runtime profile, router started-at timestamp, uptime seconds, and the
   shared build metadata payload used by `GET /version`.
3. Sanitized and bounded build metadata values in `portfolio_common.build_metadata` before they are
   exposed through `/version` or health responses.
4. Passed configured FastAPI app versions into the shared health router for both standard health
   apps and manually bootstrapped API services.
5. Updated OpenAPI examples, focused health/build metadata tests, README, operations runbook, wiki
   source, repository context, and the review ledger.

## Compatibility Impact

This is a backward-compatible response extension. Existing `status` and `dependencies` fields remain
unchanged, route paths remain unchanged, and missing build metadata remains explicit as `unknown`
without failing local health probes.

No database schema, Kafka contract, metric name, Dockerfile, image release workflow, deployment
topology, business route path, or business DTO changed.

## Validation Evidence

Commands run before commit:

```powershell
python -m pytest tests/unit/libs/portfolio-common/test_health.py tests/unit/libs/portfolio-common/test_build_metadata.py tests/unit/libs/portfolio-common/test_http_app_bootstrap.py -q
python -m ruff check src/libs/portfolio-common/portfolio_common/health.py src/libs/portfolio-common/portfolio_common/build_metadata.py src/libs/portfolio-common/portfolio_common/http_app_bootstrap.py src/services/query_service/app/main.py src/services/ingestion_service/app/main.py src/services/query_control_plane_service/app/main.py src/services/event_replay_service/app/main.py src/services/financial_reconciliation_service/app/main.py tests/unit/libs/portfolio-common/test_health.py tests/unit/libs/portfolio-common/test_build_metadata.py tests/unit/libs/portfolio-common/test_http_app_bootstrap.py --ignore E501,I001
```

Additional aggregate gates are recorded in the commit evidence.

## Documentation And Wiki Decision

README, `docs/operations-runbook.md`, `wiki/Operations-Runbook.md`, and
`REPOSITORY-ENGINEERING-CONTEXT.md` were updated because operator-facing health response truth
changed. Wiki source changed and must be published after merge.
