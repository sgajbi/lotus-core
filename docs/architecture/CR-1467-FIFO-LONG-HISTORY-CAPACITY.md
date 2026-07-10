# CR-1467: FIFO Long-History Capacity

Date: 2026-07-10
Issue: #468
Status: FIFO hardened locally; AVCO and runtime capacity pending

## Objective

Remove repeated open-lot scans from FIFO cost recalculation and provide a reproducible,
machine-readable long-history engine profile without weakening full-history correctness.

## Finding And Implementation

`FIFOBasisStrategy.get_available_quantity(...)` summed every open lot before every disposal. In a
three-buy/one-sell accumulating-lot workload, that made an otherwise linear FIFO pass grow
superlinearly as history and open-lot depth increased.

The strategy now maintains authoritative available quantity per portfolio/instrument key:

- a validated BUY adds its quantity when the lot is accepted;
- a successful SELL subtracts the exact consumed quantity after FIFO matching;
- rejected oversells and invalid inputs do not change the aggregate;
- lot order, per-lot remaining quantity, local/base cost, and source-state output remain unchanged.

An invariant test replaces the open-lot queue with an iteration-forbidden deque, then proves both
availability checks and partial disposal complete without scanning it.

## Reproducible Capacity Evidence

Added `make profile-cost-history-capacity`, backed by
`scripts/cost_history_capacity_profile.py`. It profiles the real parser, sorter, FIFO/AVCO
strategy, and cost calculator over 1,000, 2,000, 4,000, and 8,000 deterministic transactions and
writes `output/cost-history-capacity-profile.json` with schema
`lotus-core.cost-history-capacity-profile.v1`.
The workflow and profiler both use the public `build_transaction_processor(...)` application
factory, so profiling composition cannot drift behind a private helper.

On the local development host:

| Method | Rows | Duration | Throughput | Errors | Source states |
|---|---:|---:|---:|---:|---:|
| FIFO | 1,000 | 0.028418s | 35,188.965/s | 0 | 750 |
| FIFO | 2,000 | 0.062473s | 32,013.881/s | 0 | 1,500 |
| FIFO | 4,000 | 0.171129s | 23,374.152/s | 0 | 3,000 |
| FIFO | 8,000 | 0.246335s | 32,476.139/s | 0 | 6,000 |
| AVCO | 1,000 | 0.243146s | 4,112.754/s | 0 | 750 |
| AVCO | 2,000 | 0.828527s | 2,413.923/s | 0 | 1,500 |
| AVCO | 4,000 | 3.981909s | 1,004.543/s | 0 | 3,000 |
| AVCO | 8,000 | 14.203014s | 563.261/s | 0 | 6,000 |

A paired exploratory profile that included workload-object creation reduced FIFO 8,000-row time
from 1.017s to 0.320s, approximately 3.2 times faster. These local engine measurements are
characterization evidence, not a production SLO or end-to-end throughput claim.

## Validation And Compatibility

- profile, cost-basis, property-invariant, and processor tests: 33 passed;
- cost and target transaction-processing unit pack plus profile tests: 244 passed;
- combined PostgreSQL transaction-processing contract: 17 passed;
- MyPy, strict architecture/boundary, Ruff, format, documentation, and diff gates: passed.

No API, Kafka, database, cost methodology, FIFO ordering, cost/P&L, lot-state, replay, or deployment
contract changed. README and authored wiki now expose the profile command. Repository context and
both review ledgers record the constant-time FIFO invariant and the remaining AVCO risk. No central
skill change is required because the failure is a repository-specific financial-engine data
structure concern; the existing performance/review guidance already required measurement and
durable evidence.

## Remaining Work

AVCO still reconciles every historical source contribution on every disposal and is visibly
quadratic in the same workload. Optimize it in a separate correctness-first slice with exact
quantity/local/base aggregate reconciliation and direct sequential parity. Database query plans,
worker throughput, pool utilization, Kafka lag, backlog drain, failure recovery, and shutdown
drain remain required before runtime cutover.
