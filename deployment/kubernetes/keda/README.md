# Lotus Core KEDA Scaling Profiles

This folder contains KEDA `ScaledObject` definitions for calculator consumer groups.

## Intent
- Scale each calculator independently by Kafka lag.
- Preserve ordering guarantees per partition/key while increasing throughput.
- Separate hot-path and heavy-path groups with different min/max bounds.

## Prerequisites
1. KEDA installed in the cluster.
2. Kafka bootstrap DNS reachable from KEDA operator and workloads.
3. Deployments named in `calculator-scaledobjects.yaml` exist.

## Usage
1. Review and adjust namespace, bootstrap servers, and lag thresholds.
2. Apply:
   ```bash
   kubectl apply -f deployment/kubernetes/keda/calculator-scaledobjects.yaml
   ```
3. Verify:
   ```bash
   kubectl get scaledobject -n lotus-core
   kubectl describe scaledobject position-calculator-scaledobject -n lotus-core
   ```

## Tuning guidance
- Increase `maxReplicaCount` only when partition counts and DB capacity can support it.
- Use lower `lagThreshold` for low-latency calculators.
- Keep replay/heavy workloads with higher lag thresholds and wider cooldown windows.
