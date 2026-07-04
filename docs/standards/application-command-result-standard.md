# Application Command And Result Standard

Application use cases should accept command/query models and return application results. API DTOs,
framework request objects, and response DTOs belong at API adapters.

## Required Pattern

1. Routers translate API DTOs, form fields, query parameters, headers, and uploaded files into
   application command or query objects.
2. Application services accept command/query objects for use-case input and return application
   result objects for use-case output.
3. Routers translate application results into response DTOs and HTTP responses.
4. Request hashing, idempotency identity, and deterministic workflow fingerprints should use
   canonical command/query payloads, not API DTO serialization side effects.
5. Workers, consumers, schedulers, and batch flows should be able to construct commands without
   importing HTTP DTO packages.
6. Tests should cover both API mapping and application behavior.

## Current Representative Workflows

The first representative command/result migrations are:

1. Ingestion upload write workflow:
   `src/services/ingestion_service/app/application/upload_commands.py` defines
   `UploadPreviewCommand`, `UploadCommitCommand`, `UploadPreviewResult`, `UploadCommitResult`, and
   `UploadRowIssue`. `UploadIngestionService` accepts/returns those application contracts while
   `src/services/ingestion_service/app/routers/uploads.py` maps to/from upload API DTOs.
2. Query lookup read workflow:
   `src/services/query_service/app/application/lookup_catalog.py` defines portfolio, instrument,
   and currency lookup queries plus `LookupCatalogResult`. `LookupCatalogService` returns
   application results while `src/services/query_service/app/routers/lookups.py` maps results to
   the public lookup response DTO.
3. Core snapshot identity workflow:
   `src/services/query_service/app/application/core_snapshot.py` defines the canonical snapshot
   identity command used for request fingerprinting. `CoreSnapshotService` must build snapshot
   request fingerprints from that command payload instead of API DTO serialization.

## Enforcement

`make architecture-guard` runs `scripts/application_command_result_guard.py`. The guard protects
the representative migrated upload and lookup services from reintroducing API DTO imports or
response DTO return contracts, and protects core snapshot fingerprinting from returning to
`request.model_dump(mode="json")`.

## Legacy And Transitional Scope

Existing API DTO usage in broader application services remains migration backlog unless it is
covered by a representative command/result slice. Do not copy those legacy patterns into new use
cases. When touching such code, either migrate the use case to command/result contracts or document
why the migration is explicitly deferred.

## Runtime Boundary

This standard is an in-process application/API boundary. It does not create a new service, queue,
database, endpoint, or deployment topology.
