# In-Process Boundary Contract Standard

This standard turns the in-process package layout into enforceable dependency contracts for
`domain`, `application`, `ports`, `adapters`, and `proof_builders` packages.

## Boundary Rules

1. `app/domain/` owns pure domain policies, value objects, vocabulary, and deterministic business
   rules. It must not import FastAPI, Starlette, SQLAlchemy, Kafka, Redis, cloud SDKs, downstream
   clients, application services, ports, adapters, routers, repositories, API DTOs, legacy service
   packages, or persistence models.
2. `app/application/` owns use cases, commands, queries, workflow policies, command/result models,
   and application errors. It may depend on domain and ports. It must not depend on routers,
   concrete adapters, infrastructure, repositories, API DTOs, legacy service packages, or runtime
   framework objects.
3. `app/ports/` owns small capability contracts for external effects. Ports must stay
   framework-neutral and persistence-neutral; they must not import Pydantic API DTOs, SQLAlchemy
   row models, repositories, concrete adapters, infrastructure clients, routers, or legacy service
   packages.
4. `app/adapters/` and `app/infrastructure/` may depend on concrete libraries and persistence
   models while implementing ports. Domain and application packages must not import adapters
   directly.
5. `app/proof_builders/` assembles evidence from application results and domain values. Proof
   assembly must not live in routers or persistence models, and proof builders must not depend on
   FastAPI request objects, SQLAlchemy rows, repositories, or router packages.
6. Runtime wiring belongs in composition roots such as `app/dependencies.py`, routers, consumers,
   worker startup modules, or concrete infrastructure adapters.

## Controlled Exceptions

The transitional exception registry is
`docs/standards/in-process-boundary-exceptions.json`.

Each exception must include:

1. `path`
2. `rule`
3. `owner`
4. `expiresOn`
5. `followUpIssue`
6. `reason`

Exceptions are scoped to one file and one rule. They are not approval for new coupling. They are
owned migration debt and must be removed when the finding is fixed. Expired, malformed, and stale
exceptions fail the architecture guard.

## Enforcement

`make architecture-guard` runs `scripts/in_process_boundary_guard.py`.

The guard scans `src/services/**/app/domain`, `app/application`, `app/use_cases`, `app/ports`,
`app/adapters`, and `app/proof_builders`. It blocks new forbidden imports and runtime factory
calls while allowing current transitional exceptions to remain visible and expiring.

## Runtime Boundary

This is design-time modularity inside the existing deployables. It does not approve or require a
runtime service split.
