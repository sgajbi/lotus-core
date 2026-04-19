# lotus-core Architecture Index

This index provides the fastest grounded path through the `lotus-core` deep architecture set.

Use it when you need more than the README or wiki summary but do not want to scan the full
`docs/architecture/` directory blindly.

## Start Here

Read these first:

1. [lotus-core target architecture](./lotus-core-target-architecture.md)
2. [RFC-0082 contract family inventory](./RFC-0082-contract-family-inventory.md)
3. [RFC-0083 target-state gap analysis](./RFC-0083-target-state-gap-analysis.md)
4. [Query Service and Control Plane Boundary](./QUERY-SERVICE-AND-CONTROL-PLANE-BOUNDARY.md)

These four documents establish the current ownership model, downstream contract posture, and the
main RFC-0083 implementation program.

## RFC-0083 Target-Model Documents

Use these when a change touches the governed system-of-record hardening program:

1. [Portfolio Reconstruction Target Model](./RFC-0083-portfolio-reconstruction-target-model.md)
2. [Ingestion Source Lineage Target Model](./RFC-0083-ingestion-source-lineage-target-model.md)
3. [Reconciliation Data Quality Target Model](./RFC-0083-reconciliation-data-quality-target-model.md)
4. [Source Data Product Catalog](./RFC-0083-source-data-product-catalog.md)
5. [Market Reference Data Target Model](./RFC-0083-market-reference-data-target-model.md)
6. [Endpoint Consolidation Disposition](./RFC-0083-endpoint-consolidation-disposition.md)
7. [Security, Tenancy, and Lifecycle Target Model](./RFC-0083-security-tenancy-lifecycle-target-model.md)
8. [Eventing Supportability Target Model](./RFC-0083-eventing-supportability-target-model.md)
9. [Production Readiness Closure](./RFC-0083-production-readiness-closure.md)
10. [Platform E2E Runtime Validation Evidence](./RFC-0083-platform-e2e-runtime-validation-evidence.md)

## Review Ledgers And Structured Cleanup

Use these when the task is about drift, cleanup, ownership review, or historical hardening evidence:

1. [Codebase Review Playbook](./CODEBASE-REVIEW-PLAYBOOK.md)
2. [Codebase Review Ledger](./CODEBASE-REVIEW-LEDGER.md)
3. `CR-*` review records in this directory for targeted architecture and contract cleanup slices

Do not treat every `CR-*` document as mandatory reading. Use the file name to jump directly to the
relevant review stream.

## ADRs And Older Architecture References

Use these when a task requires older architectural background rather than current repo-front-door
guidance:

1. [ADR 002 Reprocessing Scalability](./adr_002_reprocessing_scalability.md)
2. [ADR 003 Integration Capabilities API](./adr_003_integration_capabilities_api.md)
3. [ADR 004 Multi-Model Core Platform](./adr_004_multi_model_core_platform.md)
4. [Microservice Boundaries and Trigger Matrix](./microservice-boundaries-and-trigger-matrix.md)

## How To Use This Index

Pick the smallest correct reading path:

1. route or API family change:
   start with RFC-0082 and the query/control-plane boundary
2. RFC-0083 slice work:
   start with the target-state gap analysis, then the specific target-model document
3. supportability or operational evidence change:
   start with the relevant RFC-0083 supportability target model and then the matching `CR-*` review
4. broad repo orientation:
   start with the target architecture and this index, then move into the wiki

## Related References

1. [Repository Engineering Context](../../REPOSITORY-ENGINEERING-CONTEXT.md)
2. [lotus-core README](../../README.md)
3. [Architecture wiki page](../../wiki/Architecture.md)
4. [API Surface wiki page](../../wiki/API-Surface.md)
