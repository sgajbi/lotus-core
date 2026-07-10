# CR-1468: Linear AVCO Source Allocation

Date: 2026-07-10
Issue: #468
Status: Hardened locally; historical backfill pending

## Objective

Remove per-disposal scans across every AVCO source contribution while preserving exact pooled
quantity, local cost, base cost, and source-level supportability evidence.

## Implementation

AVCO now changes aggregate pool state and bounded scale metadata on disposal. Source contributions
retain entry scales and generations. Materialization applies the current factors once and assigns
the exact remaining aggregate residual to the final active source, preventing cumulative rounding
drift in source-state sums.

Quantity and local/base basis have independent scales and generations. This is required because a
corporate-action basis transfer can reduce cost without changing quantity. Full disposal advances
the generation so a later acquisition cannot inherit stale source state; full basis transfer does
the same independently for local and base cost.

## Evidence And Compatibility

The deterministic 8,000-event profile reduced AVCO engine duration from 14.203 seconds to 0.363
seconds, approximately 39 times faster, with zero errors and exact aggregate reconciliation.
Focused coverage includes sequential acquisitions/disposals, equivalent sell batching, full
close/reopen, zero-basis transfer followed by acquisition, corporate-action scenarios, and exact
quantity/local/base residuals. Sixty-two focused AVCO tests and 129 cost tests passed.

This slice changed no FIFO behavior, cost/P&L formula, API, event, schema, or downstream contract.
Individual AVCO source rows remain supportability allocation, not FIFO-style disposal selection.

## Remaining Work

CR-1471 addresses workflow-level full-history replay for ordered events. CR-1479 subsequently adds
durable aggregate restoration and set-based persisted-source reconciliation with migration,
rollback, supportability, and exact aggregate parity proof. Historical pool/source backfill and
deployed database/Kafka capacity evidence remain before cutover.
