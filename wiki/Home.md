# Home

`lotus-core` is the authoritative portfolio, booking, account, holding, and transaction domain
platform for Lotus.

This wiki is the operator and onboarding map for the repo. It summarizes current implementation
truth and links to deeper docs; it is not a substitute for repo-native validation evidence.

Service profile: `domain-service`. Current posture: implementation-backed Core domain service with
heavy contract, source-data, security, and runtime validation gates. Supported claims require code,
tests, contracts, generated evidence, RFC/docs truth, and validation on the correct branch.

## What Core Does

- stores foundational private-banking portfolio and transaction truth,
- exposes operational reads for portfolio, position, transaction, cash, price, FX, and reference
  data,
- publishes governed analytics-input and source-data products for downstream Lotus services,
- supports ingestion, replay, reconciliation, lineage, readiness, and operational investigation,
- fails closed for unsupported external treasury or OMS evidence instead of fabricating readiness.

## Start By Audience

| Audience | Start here | Why |
| --- | --- | --- |
| Business, sales, and demo teams | [Supported Features](Supported-Features), [Overview](Overview), [Integrations](Integrations) | Understand what can be claimed today and which claims belong to downstream apps. |
| Operators and support teams | [Operations Runbook](Operations-Runbook), [Support and Lineage](Support-and-Lineage), [Troubleshooting](Troubleshooting) | Diagnose freshness, replay, readiness, reconciliation, and runtime issues. |
| Engineers | [Getting Started](Getting-Started), [Development Workflow](Development-Workflow), [Validation and CI](Validation-and-CI) | Install, run targeted checks, and understand the delivery lanes. |
| API and contract reviewers | [API Surface](API-Surface), [Query Control Plane](Query-Control-Plane), [RFC Index](RFC-Index) | Review route families, source-data products, and governance boundaries. |

## Primary Maps

- [Architecture](Architecture)
- [System Data Flow](System-Data-Flow)
- [Supported Features](Supported-Features)
- [API Surface](API-Surface)
- [Mesh Data Products](Mesh-Data-Products)
- [Integrations](Integrations)
- [Roadmap](Roadmap)

## Evidence Standard

| Claim type | Evidence path |
| --- | --- |
| API or route behavior | Route code, OpenAPI/route-family guards, focused tests, and [API Surface](API-Surface). |
| Source-data product support | Contract declaration, methodology doc, route metadata, trust telemetry where available, and [Mesh Data Products](Mesh-Data-Products). |
| Operational supportability | Runtime/readiness behavior, logs/metrics/traces where implemented, [Operations Runbook](Operations-Runbook), and [Support and Lineage](Support-and-Lineage). |
| Architecture boundary | Repo context, architecture docs, review ledger, and blocking guards such as `make architecture-guard`. |
| Supported feature claim | [Supported Features](Supported-Features), implementation evidence, and validation on `main`; roadmap text is not support. |

## Service And Subsystem Pages

- [Data Models](Data-Models)
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

## Most Useful Commands

```bash
make ci-local
make lotus-core-validate
make security-audit
make route-contract-family-guard
make source-data-product-contract-guard
make analytics-input-consumer-contract-guard
```

## Boundary To Remember

- `lotus-core` owns foundational portfolio-management and transaction domain truth.
- `lotus-performance`, `lotus-risk`, `lotus-advise`, `lotus-manage`, and `lotus-report` own their
  downstream conclusions and workflows.
- `lotus-platform` owns shared platform guidance, ingress, validation policy, and cross-cutting
  governance.

## Canonical References

- [Repository Engineering Context](../REPOSITORY-ENGINEERING-CONTEXT.md)
- [Target Architecture](../docs/architecture/lotus-core-target-architecture.md)
- [Architecture Index](../docs/architecture/README.md)
- [RFC-0082 Contract Family Inventory](../docs/architecture/RFC-0082-contract-family-inventory.md)
- [RFC-0083 Target-State Gap Analysis](../docs/architecture/RFC-0083-target-state-gap-analysis.md)
- [Route Contract-Family Registry](../docs/standards/route-contract-family-registry.json)
