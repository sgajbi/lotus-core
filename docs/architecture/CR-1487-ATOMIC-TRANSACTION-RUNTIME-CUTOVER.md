# CR-1487: Atomic Transaction Runtime Cutover

Date: 2026-07-10
Issue: #468
Status: App-local and CI runtime cut over; release/Kubernetes/legacy-package removal pending

## Objective

Replace the three app-local cost, cashflow, and position worker deployables with one layered
transaction-processing worker without replaying retained Kafka history, losing new bookings, or
weakening domain, replay, observability, and provenance contracts.

## Findings

1. Compose, CI runtime service sets, Prometheus, demo readiness, and load diagnostics still started
   or named the three legacy workers although the combined image and runtime were production
   composed.
2. Starting the new live group without an offset handoff can replay retained
   `transactions.persisted` data. Changing reset policy or reusing a legacy group name would either
   risk a cutover gap or retain misleading ownership.
3. The performance gate measured HTTP submission throughput, seeded no portfolio/instrument source
   records, never attempted transaction drain, and could pass while persistence retried and DLQed
   every record.
4. The performance fixture used a historical fixed date, creating unrelated valuation backfill when
   downstream services joined the stack. Bank-day log evidence also depended on generated container
   names instead of stable Compose service identities.

## Change

- Added dry-run-default, explicit-apply Kafka offset handoff for the live and replay groups. It
  requires inactive groups, zero source lag, aligned cost/cashflow live offsets, safe empty replay
  initialization, exact target writes, and post-write verification.
- Replaced three Compose services with `portfolio_transaction_processing_service`; changed all
  Compose-backed CI sets, app-local Prometheus, and demo readiness atomically.
- Retained cost, cashflow, and position as separate internal domain/application modules and retained
  compatibility events. Valuation remains independently deployable.
- Made the performance gate seed valid source records and require cost, cashflow, position, and
  combined-idempotency completion before reporting end-to-end throughput.
- Bound performance fixtures to the run business date and made the bank-day log collector use
  configurable Compose project/service identities.

## Compatibility And Rollback

Public APIs, domain event payloads, compatibility topics, database tables, and downstream response
contracts are unchanged. The app-local worker health surface moves from ports `8081`, `8082`, and
`8083` to one target on host port `8090` (container port `8085`).

Before switching environments, quiesce producers, drain and stop legacy workers, run the offset
handoff, and then start the target. Never run both topologies. Rollback requires stopping the target,
draining it, transferring reviewed offsets back to the legacy source groups or using a reviewed
checkpoint, and starting all three legacy workers together. Database rollback is not required for
the additive target runtime, but compatibility events and schema state must remain available.

## Validation

- offset planner: `8 passed`; real local dry-run/apply verified live offset `31` and empty replay
  offset `0` before target start;
- cutover/service/image contracts: `18 passed`; Compose config and image provenance passed;
- clean isolated performance gate `20260710T160722Z`: passed steady, burst, and replay profiles with
  complete transaction-domain drain and zero added DLQ pressure;
- measured completed throughput/drain: steady `6.040 tx/s` / `6.041s`, burst `7.853 tx/s` /
  `15.093s`, replay `6.321 operations/s` / `7.040s`;
- clean bank-day run `20260710T160914Z`: complete in `20.357s`, downstream drain `10.041s`, exact
  8 transaction / 8 snapshot / 8 position-timeseries / 2 portfolio-timeseries tie-out, zero open
  jobs/findings/log errors, and all API/support probes passed;
- focused MyPy, Ruff, format, architecture, image, Compose, docs, and wiki gates pass.

The throughput values are characterization evidence, not an approved production SLO. A reviewed
three-service comparison, failure injection, shutdown-under-load, CI registry evidence,
Kubernetes/KEDA cutover, canonical QA, and legacy package/shell removal remain open under #468.
