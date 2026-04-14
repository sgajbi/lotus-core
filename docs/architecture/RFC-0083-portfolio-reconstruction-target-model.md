# RFC-0083 Portfolio Reconstruction Target Model

This document is the RFC-0083 Slice 3 target model for deterministic portfolio state reconstruction in
`lotus-core`.

It does not change runtime behavior, persistence, DTOs, OpenAPI output, or downstream contracts. It
defines the target reconstruction contract that later source-data product and runtime slices must use.

## Target Principle

`lotus-core` must expose portfolio state as deterministic source truth, not as consumer-specific
analytics or report composition.

For the same reconstruction scope, `lotus-core` must return the same holdings, cash, transaction
lineage, valuation references, data-quality state, reconciliation state, and snapshot identity.

For a different reconstruction scope, `lotus-core` must produce a different snapshot identity.

## Current Implementation Baseline

Current useful building blocks:

1. `transactions` is the canonical transaction ledger, with trade, settlement, cost, FX, linked event,
   source system, and calculation-policy fields.
2. `cashflows` is the derived cash ledger produced from transaction rules, with date, epoch,
   classification, timing, and position/portfolio flow flags.
3. `position_history` records transaction-derived position state by portfolio, security,
   transaction, position date, and epoch.
4. `daily_position_snapshots` records valuation-bearing daily position snapshots by portfolio,
   security, date, and epoch.
5. `position_state` records current processing watermarks and epoch status per portfolio-security key.
6. `position_lot_state` and `accrued_income_offset_state` preserve lot and fixed-income offset lineage.
7. `/integration/portfolios/{portfolio_id}/core-snapshot` already provides a partial
   `PortfolioStateSnapshot` surface with policy, freshness, valuation context, and request
   fingerprint metadata.
8. Analytics time-series routes already use `snapshot_epoch` to stabilize paged reads.

Current gaps:

1. there is no named reconstruction scope model shared across portfolio state products,
2. snapshot identity is not yet standardized across holdings, cash, transaction windows, and source
   data products,
3. `restatement_version` is reserved by the temporal vocabulary but not persisted or exposed
   consistently,
4. `transaction_date` remains the current transaction API term; Slice 3 keeps it as current-state
   trade/event date and does not introduce a migration,
5. booking and correction semantics need a later command-model slice before runtime behavior changes.

## Reconstruction Scope

The target reconstruction scope is the minimum input set that determines a portfolio state result.

| Field | Meaning | Current-state mapping |
| --- | --- | --- |
| `portfolio_id` | Canonical portfolio identifier | `portfolios.portfolio_id` and dependent tables |
| `as_of_date` | Read-model business date represented by the result | Current query request date |
| `valuation_date` | Price/FX valuation date used by value-bearing state | Usually same as `as_of_date` today |
| `position_epoch` | Maximum position/snapshot epoch included | `position_history.epoch`, `daily_position_snapshots.epoch`, `position_state.epoch` |
| `cashflow_epoch` | Maximum cashflow epoch included | `cashflows.epoch` |
| `transaction_window_start` | Earliest transaction event included when a window is exposed | Future `TransactionLedgerWindow` scope |
| `transaction_window_end` | Latest transaction event included when a window is exposed | Future `TransactionLedgerWindow` scope |
| `source_data_products` | Named source products that contributed to the reconstruction | RFC-0083 product names |
| `policy_version` | Policy version affecting section visibility or interpretation | Current core-snapshot policy provenance |
| `restatement_version` | Historical truth version used for corrected/rebuilt state | Target field; current value is `current` |

The executable identity helper is:

1. `src/libs/portfolio-common/portfolio_common/reconstruction_identity.py`
2. `tests/unit/libs/portfolio-common/test_reconstruction_identity.py`

## Snapshot Identity Rule

The target snapshot id is derived from the canonical reconstruction scope.

Rules:

1. the identity must include portfolio, as-of date, valuation date, position epoch, cashflow epoch,
   source data product set, policy version, transaction window, and restatement version,
2. the same scope must produce the same id,
3. changing any source-scope field that can affect reconstructed truth must change the id,
4. source-data product ordering must not affect the id,
5. duplicate source-data product names must not affect the id,
6. invalid scopes must fail before an id is produced,
7. generated ids must not encode PII or customer-sensitive data directly.

`portfolio_common.reconstruction_identity.build_portfolio_snapshot_id` implements this rule using a
canonical JSON payload and SHA-256 digest. The helper is not yet wired into runtime DTOs; that wiring
belongs to later source-data product implementation slices.

## Output Products

### PortfolioStateSnapshot

Purpose: governed as-of portfolio state bundle for gateway, advise, manage, support, and simulation
consumers.

Minimum target fields:

1. `snapshot_id`,
2. reconstruction scope,
3. holdings section,
4. cash section,
5. transaction-window reference,
6. valuation input references,
7. data-quality state,
8. reconciliation state,
9. policy and freshness metadata,
10. `restatement_version`.

### HoldingsAsOf

Purpose: operational holdings and cash state for product and support use.

Minimum target fields:

1. `snapshot_id`,
2. `portfolio_id`,
3. `as_of_date`,
4. security-level quantity and valuation state,
5. cash balances by account and currency,
6. position/cash source lineage,
7. data-quality and reconciliation status.

### TransactionLedgerWindow

Purpose: deterministic transaction history window for performance, risk, report, and support.

Minimum target fields:

1. `snapshot_id` or reconstruction scope reference,
2. `portfolio_id`,
3. event window start and end,
4. transaction id,
5. transaction type,
6. `transaction_date` as current-state trade/event date,
7. `settlement_date`,
8. future `booking_date` when the booking model is implemented,
9. linked transaction group and economic event id,
10. source system, source batch, and source record lineage where available,
11. `restatement_version`.

## Lineage Requirements

Holdings lineage must be able to answer:

1. which transaction ids contributed to quantity,
2. which position epoch was used,
3. which valuation date, price, and FX source were used,
4. which lot records contributed to cost basis where cost basis is governed,
5. whether the result came from current snapshot state or fallback history.

Cash lineage must be able to answer:

1. which cashflow records contributed to each balance,
2. whether each flow was position-level, portfolio-level, internal, external, income, expense, or
   transfer,
3. which transaction id, economic event id, or linked group produced the flow,
4. which settlement/cashflow date bounded the balance,
5. which cashflow epoch was used.

Transaction lineage must be able to answer:

1. which source system supplied the transaction,
2. which source batch and source record supplied it when available,
3. which calculation policy produced costs, FX, and realized gain/loss fields,
4. which linked legs belong to the same economic event,
5. whether a future correction or restatement superseded the row.

## Restatement Decision Record

Current Slice 3 decision:

1. use `restatement_version = "current"` as the current-state identity value,
2. do not add persisted `restatement_version` columns in this slice,
3. do not expose `restatement_version` in runtime DTOs in this slice,
4. require any later correction/restatement slice to make the version explicit before downstream
   consumers migrate to restatable products,
5. never let consumers infer restatement by comparing timestamps, row counts, or payload hashes.

## Boundary Rules

`lotus-core` owns:

1. portfolio identity,
2. transaction truth,
3. cashflow derivation,
4. position state reconstruction,
5. valuation input references,
6. lot and offset lineage,
7. source-data product snapshot identity.

`lotus-core` does not own:

1. performance attribution,
2. risk interpretation,
3. advisory recommendations,
4. report narrative composition,
5. UI-specific aggregation shortcuts.

## Gaps To Close Later

| Gap | Owner slice |
| --- | --- |
| Persisted or contract-level `restatement_version` | Slice 4 or Slice 6 |
| `booking_date` command/read model | Future transaction booking hardening slice |
| Runtime use of `snapshot_id` in core snapshot DTOs | Slice 6 |
| Holdings and cash source-data product DTOs | Slice 6 |
| Transaction ledger window source-data product | Slice 6 |
| Reconciliation/data-quality status embedded in source products | Slice 5 and Slice 6 |
| Endpoint consolidation from route-specific shapes to named products | Slice 8 |

## Validation

Slice 3 validation is:

1. `python -m pytest tests/unit/libs/portfolio-common/test_reconstruction_identity.py -q`,
2. `python -m ruff check src/libs/portfolio-common/portfolio_common/reconstruction_identity.py tests/unit/libs/portfolio-common/test_reconstruction_identity.py --ignore E501,I001`,
3. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/reconstruction_identity.py tests/unit/libs/portfolio-common/test_reconstruction_identity.py`,
4. `git diff --check`,
5. `make lint`.
