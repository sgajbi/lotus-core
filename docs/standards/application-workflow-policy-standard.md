# Application Workflow Policy Standard

Application command workflows should represent idempotency, audit, correlation, command identity,
and recovery evidence as reusable application policies rather than local parameter plumbing.

## Required Pattern

1. HTTP routers map framework objects and headers into application command context at the boundary.
2. Application services should pass command identity, idempotency key, correlation IDs, causation
   IDs, and source lineage through explicit command/context objects when the workflow is reusable.
3. Idempotency semantics should be owned by an application workflow over a store port, not repeated
   as local duplicate handling in routers or infrastructure adapters.
4. Audit and recovery evidence writes should flow through an application workflow over an audit
   port, preserving fail-closed behavior where audit evidence is mandatory.
5. Tests should use fake ports and command contexts instead of FastAPI, Kafka, or database
   infrastructure when proving duplicate, conflict, audit, and failure semantics.

## Current Representative Workflow

The ingestion service owns the first representative reusable workflow policy in
`src/services/ingestion_service/app/application/workflow_policies.py`:

1. `CorrelationContext` carries correlation, request, trace, optional causation, and source-lineage
   context.
2. `ApplicationCommandEnvelope` carries command identity, endpoint, entity type, accepted count,
   idempotency key, correlation context, and request payload.
3. `IdempotencyWorkflow` coordinates ingestion job duplicate/conflict behavior through
   `IngestionJobStore`.
4. `AuditWorkflow` coordinates consumer-DLQ replay audit writes through `ReplayAuditStore`.

`IngestionJobService` remains the representative command handler and preserves its existing public
method signatures for router compatibility while routing job creation and replay audit writes
through the workflows.

## Enforcement

`make architecture-guard` runs `scripts/application_workflow_policy_guard.py`. The guard protects
the representative ingestion command path from bypassing `IdempotencyWorkflow` and `AuditWorkflow`
after those policies exist.

## Runtime Boundary

This standard is an in-process application-layer boundary. It does not create a new service, queue,
database, or runtime topology.
