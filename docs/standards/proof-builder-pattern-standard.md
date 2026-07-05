# Proof Builder Pattern Standard

Proof builders are in-process evidence assemblers for implementation-backed source-data,
supportability, replay, reconciliation, and validation proof.

## Responsibilities

Proof builders may:

1. accept typed application/domain/support inputs,
2. classify proof status and observations,
3. assemble source-safe diagnostics, lineage, evidence references, and contract artifact links,
4. return typed proof artifacts for callers to map into API DTOs, files, or validation reports.

Proof builders must not:

1. bind HTTP requests or FastAPI dependencies,
2. query SQLAlchemy sessions or persistence models directly,
3. publish Kafka records or call downstream services,
4. own repository query shape, retry loops, transactions, or runtime composition,
5. replace runbooks or documentation with unsupported claims.

## Typed Contract Families

The first shared proof-builder contract lives in
`portfolio_common.proof_builders`.

It defines typed inputs and a shared `ProofArtifact` output for:

1. `SourceDataSupportabilityProofInput`
2. `IngestionReplayEvidenceProofInput`
3. `ReconciliationEvidenceProofInput`
4. `AppValidationEvidenceProofInput`

Service-local proof builders may wrap these shared contracts when they need domain-specific input
translation, but routers and repositories should not build proof dictionaries directly.

## Placement

Use `app/proof_builders/` for service-local proof assembly when the owning service has multiple
proof surfaces. Shared reusable proof contracts may live in `portfolio_common`.

Keep API DTO mapping at routers/delivery, persistence reads in repositories/adapters, and proof
status assembly in proof builders or application-support modules.

## Runtime Boundary

Proof builders are an in-process design boundary by default. A separate proof service is allowed
only through the runtime-boundary decision record and catalog required by
`docs/standards/runtime-boundary-decision-standard.md`.

## Enforcement

`make architecture-guard` runs `scripts/proof_builder_pattern_guard.py`.

The guard validates the standard, the shared typed contract module, the focused tests, and that
routers or repositories do not import the shared proof-builder contracts directly.
