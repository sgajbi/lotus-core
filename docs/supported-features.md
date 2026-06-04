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
