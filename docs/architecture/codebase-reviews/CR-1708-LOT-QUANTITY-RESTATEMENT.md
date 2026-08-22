# CR-1708: Lot Quantity Restatement

Date: 2026-08-22
Issue: [#996](https://github.com/sgajbi/lotus-core/issues/996)
Status: Fixed locally; protected PR, exact-main, wiki publication, and issue closure pending.

## Finding

The position reducer applied same-instrument quantity corporate actions, while FIFO and AVCO lot
books retained pre-event quantities. Subsequent sales could reject valid holdings, consume too much
basis, or leave phantom quantity.

## Implemented boundary

- One `LotRestatement` retains exact before/after Decimal authorities and applies their rational
  ratio to every original/open quantity without a rounded factor.
- FIFO lots and AVCO source/pool authority precompute every replacement before mutation. Any
  non-representable lot rejects the complete event at the transaction persistence scale.
- Local/base basis is conserved; original and open quantities persist atomically in the existing
  caller-owned transaction. Calculation lineage binds the exact restatement payload.
- `quantity_restatement` is state-dependent and forces complete AVCO source-history reconstruction.
- Cost persistence carries ephemeral restatement authority to position processing. The application
  compares the position quantity at the same corporate-action transaction before cashflow,
  readiness, and commit; divergence raises non-retryable `lot_quantity_vs_position_mismatch` and
  rolls back the unit of work. This like-for-like boundary remains correct when a backdated rebuild
  includes later buys or sales whose final quantity legitimately differs.
- Restored lot books require explicit original-quantity authority. Restatement calculation failures
  map to source-safe, non-retryable `lot_quantity_restatement_rejected` outcomes instead of leaking
  raw precision detail through an untyped error.
- Calculated-output governance binds FIFO's direct numeric-policy execution. AVCO restatement is not
  listed as a separate policy execution callsite because it delegates all governed arithmetic to
  the already-bound average-cost source-allocation/materialization boundaries; the fail-closed guard
  rejects a duplicate stale boundary declaration.
- `make audit-lot-position-parity` provides a read-only ordered page (maximum 1,000 keys), assessed
  in one database round trip, for detecting historical drift without exposing transaction/lot IDs.
  Candidate selection is limited to positions with durable lot-state authority, avoiding false
  findings for cash and other non-lot products.

## Evidence

- Domain/application: exact split/reverse-split outcomes for FIFO and AVCO, partial disposal before
  restatement, repeating per-share basis, precision overflow, fail-before-mutation, typed authority,
  and rollback-before-effects parity rejection.
- PostgreSQL: FIFO and AVCO each prove BUY 100, SELL 25, split 75-to-150, duplicate delivery,
  backdated correction/epoch rebuild with identical economic lot fields, parity audit, final SELL
  150, and durable zero lot/position quantity. The source lot satisfies
  `open_quantity <= original_quantity` throughout.
- Adverse-order PostgreSQL replay: FIFO and AVCO each prove BUY, later SELL, then a backdated SPLIT
  ordered before that SELL. The split row holds 175, the final row and lot book hold 150, basis
  remains exact, and parity remains current (`2 passed in 70.20s`).
- Cross-product goldens: split-then-full-sale and reverse-split-then-full-sale run against both
  strategies and assert exact cost relief, realized P&L, and empty residual lot state.
- Warning-strict transaction-processing service unit suite: `1,934 passed in 14.70s`.
- Repository database unit lane: `18 passed in 98.39s`; restored-lot repository integration:
  `12 passed in 109.45s`.
- Transaction sell contract: `189 passed in 4.49s`; full transaction-processing contract:
  `150 passed in 891.96s`.
- Repository Ruff/format and lint governance, MyPy (`323` source files), and the complete architecture
  guard are green. Protected PR, exact-main, and release certification remain pending at this
  fixed-local documentation head.

## Compatibility and scope

Booking/event/API/database schemas, Kafka contracts, dependencies, images, and topology are
unchanged. This intentionally corrects previously wrong corporate-action economics. Parent-event
graphs and immutable disposal/transfer receipt expansion remain under #480/#481. The audit command
is additive and read-only. The Cost Calculator wiki changes and therefore requires pre-merge source
validation followed by post-main publication and strict parity.

## Reusable decision

Whenever two durable projections represent one financial invariant, preserve typed authority across
the application boundary and compare them before commit. Also provide a bounded read-only estate
audit; do not rely only on prospective rejection. This repository-local rule is now recorded in
`REPOSITORY-ENGINEERING-CONTEXT.md`; existing backend delivery and codebase-review skills already
cover the reusable platform-wide pattern, so no central skill change is required.
