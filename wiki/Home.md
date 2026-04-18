# Home

`lotus-core` is the authoritative portfolio and transaction domain platform for Lotus.

Use it for:

- foundational portfolio and transaction truth
- operational read models
- analytics-input products for downstream services
- snapshot and simulation state
- support, lineage, replay, and reconciliation control surfaces

## Start here

- [Overview](Overview)
- [Architecture](Architecture)
- [System Data Flow](System-Data-Flow)
- [Data Models](Data-Models)
- [API Surface](API-Surface)
- [Query Control Plane](Query-Control-Plane)
- [Support and Lineage](Support-and-Lineage)
- [Ingestion Service](Ingestion-Service)
- [Event Replay Service](Event-Replay-Service)
- [Persistence Service](Persistence-Service)
- [Outbox Events](Outbox-Events)
- [Cost Calculator](Cost-Calculator)
- [Cashflow Calculator](Cashflow-Calculator)
- [Financial Reconciliation](Financial-Reconciliation)
- [Position Calculator](Position-Calculator)
- [Valuation Calculator](Valuation-Calculator)
- [Timeseries and Aggregation](Timeseries-and-Aggregation)
- [Timeseries Generator Service](Timeseries-Generator-Service)
- [Getting Started](Getting-Started)
- [Development Workflow](Development-Workflow)
- [Validation and CI](Validation-and-CI)
- [Database Migrations](Database-Migrations)
- [Testing Guide](Testing-Guide)
- [Operations Runbook](Operations-Runbook)

## Important commands

```bash
make ci-local
make route-contract-family-guard
make source-data-product-contract-guard
make analytics-input-consumer-contract-guard
```

## Core boundary

- `lotus-core` owns foundational portfolio-management and transaction domain truth
- `lotus-performance` and `lotus-risk` own downstream analytics conclusions
- `lotus-platform` owns shared platform guidance, ingress, and cross-cutting governance

## Key references

- [Repository Engineering Context](../REPOSITORY-ENGINEERING-CONTEXT.md)
- [Target Architecture](../docs/architecture/lotus-core-target-architecture.md)
- [RFC-0082 Contract Family Inventory](../docs/architecture/RFC-0082-contract-family-inventory.md)
- [RFC-0083 Target-State Gap Analysis](../docs/architecture/RFC-0083-target-state-gap-analysis.md)
- [database_models.py](../src/libs/portfolio-common/portfolio_common/database_models.py)
