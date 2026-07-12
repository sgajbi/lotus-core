# CR-1481: AVCO Database Capacity Evidence

Date: 2026-07-10
Issue: #468
Status: Hardened locally; deployed latency and pool evidence pending

## Objective

Prove that bounded AVCO application restoration also has bounded database round trips, uses the
intended source-state index, and serializes only the portfolio/security key being changed.

## Evidence Design

The PostgreSQL capacity scenario seeds three independent AVCO keys with 2, 200, and 1,000 source
lots. It processes one strictly ordered disposal against the 2-source and 200-source keys while
capturing every SQL statement issued by the combined transaction-processing use case.

The same test analyzes the normalized source aggregate query with
`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`. A separate concurrency scenario holds the pool row lock
for one key, reads another key under a `200ms` lock timeout, and then attempts the locked key.

## Results

| Contract | Result |
|---|---|
| Total combined SQL statement count, 2 vs 200 sources | Equal |
| AVCO cost-state statements per ordered disposal | 5 for both source counts |
| Application source-lot materialization query | 0 |
| Source-state updates | 2 set-based statements |
| Source aggregate reads | 1 aggregate statement |
| Selective normalized aggregate index | `ix_position_lot_norm_port_sec` |
| Unrelated key while first key locked | Available |
| Same key while first key locked | Timed out as expected at `200ms` |

The five AVCO cost-state statements are one locked aggregate read, one non-residual source update,
one source aggregate read, one representative residual update, and one pool checkpoint upsert.
Source count changes affected rows and database work, but not application materialization or round
trip count.

## Validation And Compatibility

- both PostgreSQL capacity scenarios passed together in 65.91 seconds;
- the scenario used 1,202 persisted source rows and branch migrations;
- the complete transaction-processing PostgreSQL manifest owns this test module;
- source quantity/local/base reconciliation and rollback remain covered by CR-1479 and CR-1480.

No API, event, Kafka, schema, financial formula, cashflow, position, or tax-lot contract changed.
This slice adds evidence only.

## Remaining Work

This is not a deployed throughput SLO. Measure database and Kafka end-to-end events/second,
p50/p95/p99, connection-pool utilization/wait, same-key contention under expected partitioning,
consumer lag, failure recovery, and shutdown drain against the three-worker baseline before cutover.
