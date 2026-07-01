# Lotus Core Ingestion API Gold Standard Controls

This runbook summarizes the ingestion operations controls expected for production-grade usage.

## What/How/When endpoint contract

- Every ingestion endpoint description follows:
  - `What:` the business intent.
  - `How:` processing behavior and controls.
  - `When:` recommended operational usage context.
- Validation gate: `python scripts/ingestion_endpoint_contract_gate.py`
- Rate-limit scope truth gate: `make ingestion-rate-limit-scope-guard`

## Operations authorization

- Privileged operations APIs under `/ingestion/*` require `X-Lotus-Ops-Token` by default.
- After RFC 081, these protected control-plane endpoints are hosted by `event_replay_service`;
  canonical write-ingress endpoints remain on `ingestion_service`.
- Controls:
  - `LOTUS_CORE_INGEST_OPS_TOKEN_REQUIRED` (default: `true`)
  - `LOTUS_CORE_INGEST_OPS_TOKEN` (default: `lotus-core-ops-local`)
  - `LOTUS_CORE_INGEST_OPS_AUTH_MODE` (`token_only`, `jwt_only`, `token_or_jwt`; default: `token_or_jwt`)
  - `LOTUS_CORE_INGEST_OPS_JWT_HS256_SECRET` (required when JWT is used)
  - `LOTUS_CORE_INGEST_OPS_JWT_ISSUER` (optional issuer validation)
  - `LOTUS_CORE_INGEST_OPS_JWT_AUDIENCE` (optional audience validation)
  - `LOTUS_CORE_INGEST_OPS_JWT_CLOCK_SKEW_SECONDS` (default: `60`)

### Manual testing recommendation

- Keep `token_or_jwt` mode for day-to-day operations and local testing.
- Use `X-Lotus-Ops-Token` for simple manual tests.
- Use Bearer JWT only when validating federated or platform auth behavior.

## Ingestion write rate limiting

- Canonical ingestion write APIs support rolling-window rate limits.
- The default `local_process` scope is a per-process safety guard only. It is useful for local
  protection and defense in depth, but it is not a global service-level limit across multiple
  Uvicorn workers, containers, or pods.
- Scaled or production-like deployments must use an upstream gateway policy for global enforcement
  and set `LOTUS_CORE_INGEST_RATE_LIMIT_ENFORCEMENT_SCOPE` to `upstream_gateway` or
  `local_process_with_upstream_gateway`.
- Gateway-backed scopes require `LOTUS_CORE_INGEST_RATE_LIMIT_GATEWAY_POLICY_ID`; the ingestion
  service fails startup when a gateway-backed scope is selected without that policy identifier.
- `make ingestion-rate-limit-scope-guard` verifies the runtime contract and documentation continue
  to distinguish the default `local_process` safety guard from gateway-backed global enforcement
  claims.
- Rate-limit denials emitted by the local process limiter increment
  `ingestion_write_rate_limit_denials_total` with bounded `endpoint`, `reason`, and
  `enforcement_scope` labels and write a source-safe warning log.
- Controls:
  - `LOTUS_CORE_INGEST_RATE_LIMIT_ENABLED` (default: `true`)
  - `LOTUS_CORE_INGEST_RATE_LIMIT_WINDOW_SECONDS` (default: `60`)
  - `LOTUS_CORE_INGEST_RATE_LIMIT_MAX_REQUESTS` (default: `120`)
  - `LOTUS_CORE_INGEST_RATE_LIMIT_MAX_RECORDS` (default: `10000`)
  - `LOTUS_CORE_INGEST_RATE_LIMIT_ENFORCEMENT_SCOPE` (`local_process`, `upstream_gateway`,
    `local_process_with_upstream_gateway`; default: `local_process`)
  - `LOTUS_CORE_INGEST_RATE_LIMIT_GATEWAY_POLICY_ID` (required for gateway-backed scopes)

## High-value operations endpoints

- `GET /ingestion/health/consumer-lag`
- `GET /ingestion/health/error-budget`
- `GET /ingestion/jobs/{job_id}/records`
- `GET /ingestion/idempotency/diagnostics`
- `POST /ingestion/dlq/consumer-events/{event_id}/replay`
- `GET /ingestion/audit/replays`
- `GET /ingestion/audit/replays/{replay_id}`

These endpoints are designed so operations teams can triage and recover ingestion without direct DB access.
