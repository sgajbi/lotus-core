# CR-1447: Typed Remaining Lot-State Persistence

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Finding

The cost engine handed persistence only `source_transaction_id -> open_quantity`. The repository
updated quantity but left `lot_cost_base` and `lot_cost_local` at original acquisition values after
partial or full disposal. This contradicted the existing API and methodology definition of current
remaining lot cost basis.

AVCO also held remaining quantity, local cost, and base cost in parallel dictionaries, allowing
partial state or key drift to become representable.

## Change

Added immutable `OpenLotState` with domain fields:

- `quantity`;
- `cost_local`;
- `cost_base`.

FIFO derives the value from each source `CostLot`. AVCO stores one `OpenLotState` per source
transaction and reconciles source values pro rata to pooled holdings, assigning residuals to the
final source so aggregate quantity and cost remain exact. `TransactionProcessor`,
`CostCalculationWorkflow`, and `CostCalculatorRepository` now pass and persist that value directly.

The obsolete quantity-only processor/repository handoff and redundant FIFO quantity map were
removed. A stale disposition annotation was corrected to include consumed quantity.

## Compatibility Impact

Schema, route, response field, topic, and event names are unchanged. Values intentionally change:

- partially open FIFO lots now carry remaining rather than original cost basis;
- fully closed lots carry zero remaining quantity and zero remaining basis;
- AVCO source rows remain open and reconcile to pooled quantity/cost while holdings remain.

Historical rows can retain old values and require a governed idempotent backfill with rollback and
source-product validation before current-history claims are made.

## Validation

- focused strategy, processor, workflow, and repository unit tests: 67 passed;
- direct cost-repository plus combined transaction PostgreSQL paths: 12 passed;
- focused MyPy and Ruff passed;
- documentation and wiki source updated to current domain semantics.
