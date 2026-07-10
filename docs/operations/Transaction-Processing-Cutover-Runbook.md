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
   python scripts/transaction_processing_cutover_offsets.py \
     --bootstrap-servers localhost:9092 \
     --output output/transaction-processing-offset-cutover-dry-run.json
   ```

4. Review every partition, source/target group, high watermark, and `requires_write` value.
5. Apply and verify exact target offsets:

   ```bash
   python scripts/transaction_processing_cutover_offsets.py \
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
6. Run the bank-day scenario with the active Compose project and require exact DB/API/log tie-out.

## Stop And Roll Back

Stop the rollout if source groups are active, source lag is non-zero, legacy live offsets differ,
the target group cannot be verified, readiness fails, DLQ grows, or domain completion times out.

For rollback, quiesce producers, drain and stop the target, review current target offsets, transfer
an approved checkpoint to all required legacy groups, then start the three legacy workers together.
Do not reset to earliest/latest and do not infer offsets from timestamps.
