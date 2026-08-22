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
  compares the resulting position quantity before cashflow, readiness, and commit; divergence raises
  non-retryable `lot_quantity_vs_position_mismatch` and rolls back the unit of work.
- `make audit-lot-position-parity` provides a read-only ordered page (maximum 1,000 keys), assessed
  in one database round trip, for detecting historical drift without exposing transaction/lot IDs.

## Evidence

- Domain/application: exact split/reverse-split outcomes for FIFO and AVCO, partial disposal before
  restatement, repeating per-share basis, precision overflow, fail-before-mutation, typed authority,
  and rollback-before-effects parity rejection.
- PostgreSQL: FIFO and AVCO each prove BUY 100, SELL 25, split 75-to-150, duplicate delivery,
  backdated correction/epoch rebuild with identical economic lot fields, parity audit, final SELL
  150, and durable zero lot/position quantity. The source lot satisfies
  `open_quantity <= original_quantity` throughout.
- Cross-product goldens: split-then-full-sale and reverse-split-then-full-sale run against both
  strategies and assert exact cost relief, realized P&L, and empty residual lot state.
- Scoped Ruff and repository MyPy are green. Final repository-native transaction and release gates
  remain pending at this fixed-local documentation head.

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
