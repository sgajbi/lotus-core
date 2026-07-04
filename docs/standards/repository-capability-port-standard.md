# Repository Capability Port Standard

Application and source-data use cases must depend on the smallest repository capability they need,
not on broad concrete repositories as de facto application contracts.

## Required Pattern

1. Define a protocol for the use case capability, such as a source-data reader, evidence reader,
   run writer, or session store.
2. Keep returned record types explicit. Prefer read-record dataclasses or governed ORM/domain
   models already used by the boundary.
3. Keep concrete SQLAlchemy repositories as adapters that can implement multiple ports.
4. Use fake ports in unit tests for orchestration and failure behavior.
5. Add a static guard when a concrete repository dependency is likely to return.

## Current Representative Ports

The current representative ports are:

1. `PortfolioTaxLotReader` for the `PortfolioTaxLotWindow:v1` source-data use case.
2. `ReconciliationRunWriter`, `PositionValuationEvidenceReader`,
   `TransactionCashflowEvidenceReader`, and `TimeseriesIntegrityEvidenceReader` for financial
   reconciliation workflows.

## Enforcement

`make architecture-guard` runs `scripts/repository_port_guard.py`. The guard blocks the
representative source-data and reconciliation paths from reverting to broad concrete repository
annotations once a narrow port exists.

## Runtime Boundary

This standard improves design-time modularity inside existing deployables. It does not require a
new process, database, queue, or service split. Runtime splits require separate scalability,
resilience, security-isolation, and ownership evidence.

