# Transaction Processing Cutover Runbook

Use this runbook when replacing the legacy cost, cashflow, and position worker deployment with
`portfolio_transaction_processing_service`. The three internal financial modules remain distinct;
only their runtime shell and normal-path transaction boundary are consolidated.

## Preconditions

1. Target image release manifest, SBOM, vulnerability scan, signature, provenance, and digest are
   verified for the exact Git SHA.
2. Schema migrations are complete and historical AVCO reconciliation evidence is reviewed.
3. Legacy live groups are at zero lag and cost/cashflow offsets are equal for every
   `transactions.persisted` partition.
4. Producers can be quiesced for the offset handoff window.
5. Target and legacy topology must never run concurrently.

## Handoff

1. Quiesce transaction producers and verify no new `transactions.persisted` records arrive.
2. Drain and stop all three legacy worker deployables.
3. Audit the handoff without mutation:

   ```bash
   python scripts/operations/transaction_processing_cutover_offsets.py \
     --bootstrap-servers localhost:9092 \
     --output output/transaction-processing-offset-cutover-dry-run.json
   ```

4. Review every partition, source/target group, high watermark, and `requires_write` value.
5. Apply and verify exact target offsets:

   ```bash
   python scripts/operations/transaction_processing_cutover_offsets.py \
     --bootstrap-servers localhost:9092 \
     --apply \
     --output output/transaction-processing-offset-cutover-apply.json
   ```

6. Start only `portfolio_transaction_processing_service` and resume producers.

## Validation

1. `GET http://localhost:8090/health/ready` returns ready for database, Kafka, and worker runtime.
2. `GET http://localhost:8090/version` matches the deployed image/release manifest metadata.
3. Live and replay committed lag converge without DLQ growth.
4. Cost, cashflow, position, idempotency, and outbox effects complete atomically.
5. Run `make test-performance-load-gate`; use completed transaction throughput, not request
   submission rate.
6. Run `make test-failure-recovery-gate`. The gate must interrupt
   `portfolio_transaction_processing_service`, prove committed live-group lag growth, and return
   live/replay lag to baseline with exact cost/cashflow/position/claim counts and no added DLQ event.
7. Run the bank-day scenario with the active Compose project and require exact DB/API/log tie-out.

## Controlled Local Image Rehearsal

The consumer-group handoff above moves from the retired calculator groups to the unified runtime.
It does not prove that a qualified transaction-service image can be canaried and rolled back while
retaining the unified group's offsets. Use the separate release rehearsal for that evidence.

First generate and review a non-mutating plan:

```bash
make transaction-release-rehearsal-plan \
  TRANSACTION_RELEASE_CANDIDATE_MANIFEST=output/releases/candidate.json \
  TRANSACTION_RELEASE_ROLLBACK_MANIFEST=output/releases/rollback.json \
  TRANSACTION_RELEASE_OUTPUT=output/task-runs/transaction-release-plan.json
```

The plan requires two distinct, supply-chain-qualified digest manifests and a clean exact source
revision. It records `mutates_runtime=false` and `cluster_certification=false`.

Execute only from the exact candidate Git SHA after reviewing the plan:

```bash
make transaction-release-rehearsal \
  TRANSACTION_RELEASE_CANDIDATE_MANIFEST=output/releases/candidate.json \
  TRANSACTION_RELEASE_ROLLBACK_MANIFEST=output/releases/rollback.json \
  TRANSACTION_RELEASE_OUTPUT=output/task-runs/transaction-release-receipt.json \
  TRANSACTION_RELEASE_PULL_IMAGES=true
```

Execution creates one generated `lotus-integration-transaction-release-rehearsal-*` project. It
starts the prior digest, runs a fixed baseline canary, stops only the transaction worker, proves the
stable live group is inactive and drained, recreates only that worker with the candidate digest,
runs the candidate canary, restores the prior digest, and runs a rollback canary. PostgreSQL and
Kafka remain running across the two image changes. Every canary requires exact transaction, cost,
cashflow, position, processing-claim, outbox, DLQ, duplicate-effect, and reconciliation evidence.
Release manifests may contain only the governed Git SHA, branch, build timestamp, repository URL,
image version, and CI run ID runtime metadata. The runner rejects database URLs, port settings,
Compose controls, and any other environment override before it prepares Docker resources. DLQ
growth is measured from durable consumer-DLQ rows scoped to the stable transaction group and source
topic, not inferred from the readiness payload.

The terminal receipt is redacted and content-hashed. A passing receipt also proves zero remaining
containers, networks, or volumes with the exact generated project label. The adapter cannot target
`lotus-core-app-local`, does not run Docker prune, and does not certify Kubernetes rollout,
multi-replica behavior, production traffic, alert routing, or rollback RTO. Those remain
post-merge environment evidence.

## Stop And Roll Back

Stop the rollout if source groups are active, source lag is non-zero, legacy live offsets differ,
the target group cannot be verified, readiness fails, DLQ grows, or domain completion times out.

For rollback, quiesce producers, drain and stop the target, review current target offsets, and deploy
the previous certified target digest with the same target group identities. The three legacy worker
images/shells are retired and must not be recreated as an incident shortcut. Do not reset to
earliest/latest and do not infer offsets from timestamps.
