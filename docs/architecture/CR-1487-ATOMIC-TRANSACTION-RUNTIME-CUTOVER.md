# CR-1487: Atomic Transaction Runtime Cutover

Date: 2026-07-10
Issue: #468
Status: App-local/CI and Kubernetes manifests cut over; registry/cluster/legacy removal pending

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
5. The failure-recovery gate paused persistence, observed ingestion-job backlog, submitted invalid
   historical trades, and accepted a drain timeout as bounded recovery. It did not interrupt or
   certify the unified transaction consumer.

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
- Replaced the failure proxy with a fail-closed unified-consumer test. It pauses the target Compose
  service, proves committed live-group lag grows by the submitted valid record count, verifies source
  persistence during interruption, resumes the worker, and requires exact cost, cashflow, position,
  idempotency-claim, live-lag, replay-lag, and incremental DLQ outcomes.
- Removed legacy transaction images from CI prebuild/release inventories. Added a hardened target
  Kubernetes Deployment, Service, ServiceAccount, disruption budget, and one KEDA scaler with live
  and replay triggers. CI renders the deployment only from the target's signed, scanned,
  provenance-backed release manifest and preserves one digest across dev, UAT, and prod.

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
- unified failure-recovery run `20260710T163435Z`: target paused for `10.107s`; source persisted
  `100` records in `2.020s`; committed live lag grew `0 -> 100` and returned to `0`; replay lag
  remained `0`; exact `100` cost / cashflow / position / processing-claim outcomes completed in
  `9.149s`; no DLQ event was added;
- focused MyPy, Ruff, format, architecture, image, Compose, docs, and wiki gates pass;
- Kubernetes/release contracts: `37 passed`; base and KEDA Kustomize rendering and image provenance
  guard passed.

The throughput values are characterization evidence, not an approved production SLO. A reviewed
three-service comparison, shutdown-under-load, pool-pressure evidence, CI registry publication and
cluster rollout evidence, canonical QA, and legacy package/shell removal remain open under #468.
