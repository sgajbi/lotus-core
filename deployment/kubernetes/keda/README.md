# Lotus Core KEDA Scaling Profiles

This folder contains KEDA `ScaledObject` definitions for transaction processing, valuation, and
timeseries consumer groups.

## Intent
- Scale unified cost/cashflow/position processing from its live and replay consumer-group lag.
- Keep valuation and timeseries scaling independent because they own different workloads.
- Preserve ordering guarantees per partition/key while increasing throughput.
- Separate hot-path and heavy-path groups with different min/max bounds.

## Prerequisites
1. KEDA installed in the cluster.
2. Kafka bootstrap DNS reachable from KEDA operator and workloads.
3. The deployments referenced by `processing-scaledobjects.yaml` exist.
4. The transaction-processing Kafka offset handoff has completed before its first pod starts.

## Usage
1. Review namespace and bootstrap servers. Change lag or replica bounds only with partition, DB pool,
   and recovery evidence.
2. Apply:
   ```bash
   kubectl apply -k deployment/kubernetes/keda
   ```
3. Verify:
   ```bash
   kubectl get scaledobject -n lotus-core
   kubectl describe scaledobject portfolio-transaction-processing -n lotus-core
   ```

## Tuning guidance
- Increase `maxReplicaCount` only when partition counts and DB capacity can support it.
- Both transaction triggers scale the same deployment; KEDA uses the highest requested replica count.
- The target groups must have reviewed committed offsets. `earliest` is the fail-safe policy if that
  invariant is broken; it prevents silent message loss and should trigger rollback/incident review.
- Preserve per-partition ordering and do not scale beyond useful topic partition concurrency.
