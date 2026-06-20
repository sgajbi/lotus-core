# lotus-core Supported Features

## Current Supported Capability Families

`lotus-core` currently supports:

1. portfolio and instrument master data,
2. transaction ingestion and booking foundations,
3. position, valuation, cashflow, and time-series foundations,
4. operational read-plane query APIs,
5. governed query-control-plane source-data products,
6. ingestion and persistence support surfaces,
7. reconciliation, supportability, lineage, and operational evidence APIs,
8. DPM and front-office source-data product support where declared in repository contracts.

## Supported Surface Families

The app-level validation command treats these implementation-backed surface families as the current
Core support map:

1. Portfolio and account source of record
2. Transaction and booking evidence
3. Position, valuation, and cashflow calculators
4. Operational read plane
5. Query control plane
6. DPM source-data products
7. Ingestion and replay
8. Reconciliation and supportability
9. Simulation and advisory source effects

## Boundary Statement

Supported features must be implementation-backed. This document should not be used to claim
capabilities that are only planned, mocked, or fail-closed pending external bank-owned data
ingestion.

## Evidence Sources

1. `REPOSITORY-ENGINEERING-CONTEXT.md`
2. `docs/standards/route-contract-family-registry.json`
3. `docs/architecture/CODEBASE-REVIEW-LEDGER.md`
4. `docs/methodologies/source-data-products/`
5. `contracts/domain-data-products/`
6. `make lotus-core-validate`, which runs app-level supported-surface validation, seeds
   deterministic synthetic data through the runtime smoke path, calls real Core APIs and
   calculations, checks contract/doc truth, writes JSON evidence under
   `output/lotus-core-validation/`, and exits non-zero on weak proof.
