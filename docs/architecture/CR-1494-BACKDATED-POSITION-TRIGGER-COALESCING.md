# CR-1494: Backdated Position Trigger Coalescing

Date: 2026-07-11
Issues: #486, #468
Status: Implemented locally; deployed workload baseline pending

## Objective

Ensure a burst of backdated transactions for one portfolio/security produces one current-epoch
position rebuild when the first rebuild already materialized every committed trigger.

## Finding

The unified runtime already rebuilt position history inline and emitted no legacy replay fan-out.
Compare-and-set epoch advancement coalesced true overlapping losers, but a second worker that
started after the first commit could still see a backdated business date, advance another epoch,
and rebuild the same committed history again.

## Implementation

- Added an application-level current-epoch materialization decision before epoch advancement.
- Added `PositionRepository.is_transaction_materialized()` as a bounded lineage existence query.
- Added normalized portfolio/security/epoch/transaction index
  `ix_pos_hist_norm_port_sec_epoch_txn` and Alembic revision `c109b2c3d4ee`.
- Recorded already-materialized triggers as `coalesced/already_materialized`; they perform no epoch
  advance, history read, delete/reinsert, or replay publication.
- Added `position_recalculation_work_items` with bounded `inline_rebuild`, `legacy_replay`, and
  `coalesced` modes plus a dashboard p95 work-volume panel.

The check executes only after the pure position policy classifies an original event as backdated.
Normal ordered processing therefore receives no additional query.

## Correctness Evidence

A PostgreSQL test first materializes a current BUY, commits two earlier BUY transactions, and then
processes both backdated events concurrently through the complete transaction-processing use case.
The portfolio/security cost lock serializes the two units of work. The first winner advances epoch
`0 -> 1` and rebuilds all three committed transactions. The second sees its own lineage in epoch
`1` and coalesces.

Final current-epoch quantities are `5`, `8`, and `18`; cost bases are `50`, `80`, and `180`.
The two results contain position work counts `3` and `0`, and no
`ReprocessTransactionReplay` outbox event exists.

## Architecture And Compatibility

The pure backdated-date policy remains in the position domain reducer. The application workflow
owns the decision to skip already materialized work, the repository adapter owns the indexed SQL,
and the unified unit of work owns serialization and commit. No controller, delivery consumer, or
domain model accesses persistence directly.

No public API or event payload changed. The active app-local/CI runtime already uses inline rebuild
and publishes zero internal replay events. The legacy queue mode remains compatibility-only code;
its work volume is now observable until its final removal slice. The additive index requires normal
migration rollout and downgrade support.

## Validation

- Position repository/model/workflow cohort: `79 passed`.
- Position workflow and dashboard cohort: `56 passed`.
- PostgreSQL concurrent backdated scenario: `1 passed in 28.07s`.
- Repository-native transaction-processing contract: `32 passed in 126.98s`.
- Alembic single head `c109b2c3d4ee`; migration SQL contract passed.
- Ruff and MyPy passed for touched Python modules.
- Wiki/docs, strict architecture, domain-layer, dependency-inversion, repository-transaction,
  modularity, and in-process boundary gates passed.

## Remaining Deployment Evidence

Capture inline rebuild and coalesced work-volume distributions, epoch-advance/coalescing rates,
position/cost lock waits, database pool use, transaction latency, lag, and recovery under a
controlled backdated burst. Set alert thresholds only after reviewing that baseline. No platform
skill change is required because the existing backend, issue-resolution, and codebase-review skills
already require bounded coalescing, real concurrency proof, telemetry, and same-pattern guidance.
