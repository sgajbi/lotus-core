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
  non-representable lot or pool/source segment rejects the complete event at the transaction
  persistence scale without partially mutating the in-memory strategy.
- AVCO materialization caps each preliminary open-quantity share by its source original quantity,
  then assigns the exact storage-quantum residual deterministically across remaining source
  headroom. Aggregate quantity that cannot be represented without violating source authority fails
  closed instead of over-allocating the final source lot. Residual candidates are fenced to the
  current source-allocation generation consistently with materialized quantities and disposal
  factors.
- Historical AVCO reconciliation persists the rebuilt state's restated original quantity alongside
  open quantity and basis. It does not reconstruct original authority from the pre-action BUY
  payload while claiming a successful repair. Its currentness fence compares the deterministic
  original quantity of every source, so an otherwise-consistent estate repaired by an older writer
  cannot retain stale source authority.
- FIFO/AVCO disposal allocations carry strategy-owned original and pre-disposal quantities.
  Amortized-cost overlays therefore allocate carrying amount after a split from the restated lot,
  never from the immutable pre-action BUY quantity.
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
- CI fix-forward: the full warning gate exposed an interleaved AVCO buy/disposal sequence where the
  former last-source residual shortcut produced open quantity `1.0000000002` against original
  quantity `1`. A deterministic six-source domain regression now proves exact aggregate
  reconciliation, source-level `open <= original`, stable residual placement, and fail-closed
  rejection when aggregate quantity exceeds total source authority. The focused pack passes
  `23` tests and the complete warning gate passes with zero warnings.
- Review fix-forward: direct repository tests prove forward- and reverse-restated originals replace
  the source transaction quantity during AVCO rebuild. Real PostgreSQL reconciliation now repairs a
  two-BUY, forward-SPLIT, partial-SELL history to original quantities `200/200`, open quantities
  `175/175`, and conserved pool/source basis `1,925`; the repair is idempotent (`1 passed in
  69.26s`). The complete cost repository pack passes `40` tests.
- Final unresolved-thread reconciliation: an AVCO basis-transfer/disposal sequence proves a
  non-representable pool segment rejects before source or pool mutation; a direct residual proof
  prevents stale-generation revival; and the position application/port result now carries only the
  corporate-action-row quantity actually consumed by the parity fence. The focused domain,
  application, and adapter pack passes `105` warning-strict tests.
- Coverage fix-forward: the lot-position audit domain now directly rejects blank identities,
  negative epoch/lot authority, and falsely current assessments. Its line and branch coverage are
  `100%`; the four added invariant exits move financial-calculation branch coverage from `84.95%`
  to a calculated `85.47%` and changed critical-code branch coverage from `84.71%` to `85.24%`
  without changing thresholds or excluding source.
- Final financial review: a split-before-disposal amortized-cost golden proves original/open
  authority `200/200`, disposal `50`, and exact carrying-cost relief `24.25` rather than the stale
  pre-split `48.5`. AVCO reconciliation now detects valid-lineage source-original drift, repairs
  `175/225` back to planner authority `200/200`, and returns CURRENT on repeat (`15 passed in
  71.49s`). The parity audit applies normalized identifier semantics to both lot and position-history
  correlations, preventing padded legacy identifiers from disappearing from evidence.
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
audit; do not rely only on prospective rejection. Residual allocation must conserve the aggregate
without violating any component's authority; never repair aggregate rounding by blindly assigning
the remainder to one final component. This repository-local rule is now recorded in
`REPOSITORY-ENGINEERING-CONTEXT.md`; existing backend delivery and codebase-review skills already
cover the reusable platform-wide pattern, so no central skill change is required.
