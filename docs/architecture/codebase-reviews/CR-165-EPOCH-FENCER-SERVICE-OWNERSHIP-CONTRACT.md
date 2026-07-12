## CR-165: Epoch fencer service ownership contract

### Finding

`EpochFencer` still allowed `service_name` to default to `"<not-set>"`. That meant one of the core stale-epoch control metrics could silently lose real ownership if a caller forgot to provide the service name.

For a banking-grade replay and idempotency fence, that is too weak. Metric ownership should be explicit, not optional.

### Fix

Made `service_name` mandatory on `EpochFencer` construction and updated the shared unit proofs to require an explicit owner.

### Why this matters

This removes a silent observability failure mode on an active control path. A stale event drop is only operationally useful if it is attributable to the actual service that dropped it.

### Follow-up

Any future fencing helper should require explicit service ownership at construction time instead of offering a sentinel default.
