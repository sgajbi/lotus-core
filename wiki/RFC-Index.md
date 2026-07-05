# RFC Index

## Current Scope

This page is the wiki navigation view. The full governed inventory lives in
[`docs/standards/rfc-status-ledger.v1.json`](../docs/standards/rfc-status-ledger.v1.json) and is
checked by `make rfc-status-ledger-guard`.

The ledger covers:

| Family | Coverage | Why It Matters |
|---|---|---|
| Core RFCs | `docs/RFCs/RFC*.md` plus the human `RFC-INDEX.md` and delta backlog | Prevents historical or partial RFCs from being mistaken for current behavior. |
| Transaction RFCs | `docs/rfc-transaction-specs/**/*.md` | Keeps transaction specifications tied to the canonical transaction type registry and supported-feature claims. |
| Architecture RFC material | `docs/architecture/RFC-*.md` | Connects RFC-0082/RFC-0083 target models and closure evidence to current architecture truth. |
| Operations RFC playbooks | `docs/operations/RFC-*.md` | Keeps operator-facing RFC playbooks statused with the same metadata standard. |

New RFC files must be added to the ledger in the same slice, with owner, status, evidence,
docs/wiki links, supported-feature posture, and supersession/deprecation metadata.

## Most relevant current RFCs

- `RFC-0082`
  downstream domain-authority and analytics-serving boundary hardening
- `RFC-0083`
  system-of-record target architecture
- `RFC-0072`
  CI and validation governance
- `RFC-0067`
  API vocabulary and OpenAPI governance
- `RFC-0108`
  front-office analytics UI observability and operational posture; `lotus-core` implements the
  `core.observability.portfolio_supportability` source supportability slice through bounded
  readiness response fields and bounded Prometheus metric labels.

## Key local references

- [Architecture Index](../docs/architecture/README.md)
- [RFC-0082 Contract Family Inventory](../docs/architecture/RFC-0082-contract-family-inventory.md)
- [RFC-0083 Target-State Gap Analysis](../docs/architecture/RFC-0083-target-state-gap-analysis.md)
- [RFC-0083 Production Readiness Closure](../docs/architecture/RFC-0083-production-readiness-closure.md)

## Use this page when

- a route or API family change needs the right governing RFC first
- a system-of-record hardening slice needs the right RFC-0083 target-model document
- a reviewer needs the shortest path from wiki summary into the deep architecture set

## Fast reading paths

Route-family or downstream contract work:

1. [RFC-0082 Contract Family Inventory](../docs/architecture/RFC-0082-contract-family-inventory.md)
2. [Query Control Plane](Query-Control-Plane)
3. [API Surface](API-Surface)

RFC-0083 slice work:

1. [RFC-0083 Target-State Gap Analysis](../docs/architecture/RFC-0083-target-state-gap-analysis.md)
2. [Architecture Index](../docs/architecture/README.md)
3. the specific RFC-0083 target-model document for the slice

Validation or readiness review:

1. [Validation and CI](Validation-and-CI)
2. [RFC-0083 Production Readiness Closure](../docs/architecture/RFC-0083-production-readiness-closure.md)
3. [Operations Runbook](Operations-Runbook)
