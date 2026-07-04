# Ingestion Workflow Store Port Standard

Ingestion application workflows that need durable job lifecycle, idempotency, replay audit, DLQ,
or operational-control evidence must depend on explicit store ports before they depend on concrete
SQLAlchemy helpers.

## Required Pattern

1. Application services accept a typed store port through constructor injection.
2. Default runtime wiring may use SQLAlchemy-backed adapters, but the orchestration method should
   call the port, not helper functions with `get_async_db_session`.
3. Idempotency stores must define same-key behavior:
   - same endpoint, same idempotency key, same payload returns the existing job/result,
   - same endpoint, same idempotency key, different payload raises the governed idempotency
     conflict error.
4. Replay audit stores must fail closed. If durable audit persistence is unavailable, the workflow
   raises the typed audit-write failure and must not acknowledge replay success.
5. Diagnostic metadata must remain source-safe. Event ids, replay fingerprints, correlation state,
   endpoint, actor, status, and missing-correlation reason are allowed. Raw request payloads,
   secrets, tokens, and source files are not.

## Enforcement

`make architecture-guard` runs `scripts/ingestion_store_port_guard.py`. The guard blocks
`IngestionJobService` from directly calling job creation/idempotency and replay-audit helper
functions that bypass the new store ports.

## Current Scope

The current implemented representative ports are:

1. `IngestionJobStore`
2. `ReplayAuditStore`
3. catalog protocols for audit diagnostics, consumer DLQ events, and operational controls

Broader repository, unit-of-work, and publisher ports remain separate issue slices.

