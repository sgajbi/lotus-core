# CR-1517: Shared Domain Library Boundary

Date: 2026-07-11
Issue: #468 same-pattern architecture scan
Status: Implemented locally; broader library decomposition pending

## Objective

Reduce the unstructured `portfolio_common` root surface while preserving cross-service transaction
contracts and behavior.

## Finding

The shared distribution contained 107 Python files and 21,682 lines spanning domain policy,
persistence, Kafka, HTTP, OpenAPI, orchestration, and runtime support. Transaction control-code
normalization existed at the package root and behind a second transaction-domain facade. An unused
generic `models.py` retained legacy transaction and health DTOs with no production or test imports.

## Implementation

- Added the framework-independent `portfolio_common.domain` namespace.
- Moved canonical transaction control-code normalization into that namespace and redirected event,
  ingestion, cashflow, position, and transaction-domain consumers.
- Removed the duplicate transaction-domain facade and the unused generic DTO module.
- Added AST-based guards preventing retired imports and framework, persistence, HTTP, or messaging
  dependencies from entering the shared domain namespace.

## Boundary Decision

`portfolio_common` is a distribution boundary, not an architecture layer. Only capabilities with
multiple legitimate service consumers and one stable shared contract belong there. Shared domain
policy belongs under `portfolio_common.domain`; repositories, clients, runtime adapters, and
service-owned orchestration require separate ownership review before relocation. Import fan-in
alone does not prove correct ownership.

## Compatibility

No API, DTO field, event payload, transaction classification, calculation, database schema, Kafka
topic, metric, deployment topology, or downstream contract changed. The retired modules had no
supported external contract; repository consumers now use the explicit domain path.

## Validation

- Transaction domain, ingestion DTO, and characterization cohort: `195 passed`.
- Cashflow and position cohort: `157 passed`.
- Ownership guard: `3 passed`.
- Ruff, formatting, scoped MyPy, in-process boundary guard, and diff checks passed.
- Reconciliation onto the post-PR-727 mainline reran ownership, import, Ruff, MyPy, architecture,
  documentation, and diff checks; broader transaction contracts remain in the aggregate gate.

## Follow-Up

Classify the remaining root modules by consumer set, state/transaction ownership, and dependency
type. Prioritize service-owned repositories and orchestration for relocation; retain stable event,
identity, money, runtime-port, and supportability contracts until replacement consumers are proven.
