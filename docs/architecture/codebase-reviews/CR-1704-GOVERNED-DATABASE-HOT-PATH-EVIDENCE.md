# CR-1704 - Governed Database Hot-Path Evidence

Date: 2026-08-22
Status: Fixed locally; protected PR, exact-main validation, wiki publication, and issue closure pending
Issue: #510

## Finding

Core had performance-oriented indexes, migrations, latency tests, and isolated PostgreSQL plan
assertions, but no one repository-native command could reproduce plan and row-count posture across
the critical transaction, holdings, valuation, and support query families. Small fixtures could
therefore remain green while a retained-history scan emerged at representative book volume.

## Resolution

1. A versioned catalog owns scenario identity, production repository method, deterministic seed
   cardinality, prohibited nodes, indexed-access posture, and row-count ceilings.
2. `make database-hot-path-evidence` runs seven exact PostgreSQL test nodes and assembles twelve
   scenarios: latest positions, operations support paging, reconciliation controls, transaction
   ledger count/page, valuation and reprocessing claims, and valuation and reprocessing stale
   selection/reset paths. Reprocessing claim evidence includes both its duplicate-normalization CTE
   and its subsequent bounded claim update.
3. Every scenario captures the SQL emitted by the production repository method. SQL and binds are
   ephemeral; the retained artifact contains only bounded row metrics, node types, index names,
   sequential-scan relation names, violations, source SHA, and deterministic content identity.
4. Read statements use `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`. Mutating statements are captured
   before production execution, then explained inside a connection-level transaction that can
   return the plan only by crossing the mandatory rollback boundary. Fresh-session comparisons of
   every mutable claim and recovery field prove durable authority remains unchanged.
5. Rows examined include rows emitted and rows discarded by filters, index rechecks, and join
   filters, multiplied by actual loops. Fragment assembly re-derives status and violations from
   the catalog and rejects missing, extra, malformed, contradictory, misidentified, or unsafe
   evidence. The
   command refuses a dirty tree and rechecks the source SHA after PostgreSQL execution so concurrent
   edits cannot be bound to an untested revision.
6. Evidence remains explicitly `report_only`. A complete artifact can truthfully contain failed
   scenarios without making the command fail. Test, catalog, fragment, source-integrity, or artifact
   failures still fail the command closed.

## Measured Result

The exact clean-head command at signed SHA `e6190f904819e0f06447f16047367145af964c49`
completed seven PostgreSQL nodes in 125.74 seconds and produced twelve results:

| Scenario | Status | Root rows | Rows examined | Finding |
| --- | --- | ---: | ---: | --- |
| latest position snapshot | passed | 500 | 28,500 | indexed; no sequential scan or `WindowAgg` |
| operations support page | passed | 100 | 1,200 | indexed; bounded support ordering |
| reconciliation estate scan | passed | 1,000 | 3,000 | indexed exact-scope read |
| reprocessing claim normalization | failed | 1 | 35,001 | sequential scan and `WindowAgg`; routed to #988 |
| reprocessing job claim | passed | 1,000 | 17,000 | indexed bounded claim |
| reprocessing stale reset | passed | 0 | 5,000 | indexed bounded update |
| reprocessing stale scan | passed | 1,000 | 7,000 | indexed bounded recovery cohort |
| transaction ledger count | passed | 1 | 2,001 | indexed portfolio count |
| transaction ledger page | failed | 100 | 11,400 | sequential scan of `transactions`; routed to #506 |
| valuation job claim | failed | 1,000 | 21,001 | sequential scan of `portfolio_valuation_jobs`; routed to #985 |
| valuation stale reset | passed | 1,000 | 2,000 | primary-key indexed bounded update |
| valuation stale scan | failed | 1,000 | 13,000 | sequential scan of `portfolio_valuation_jobs`; routed to #987 |

The retained content identity was
`sha256:b015a9c70e3920109a6a6c475ff04a0465a6dee0261d90d895abb3eff5b3199e`.
The generated file is local evidence under `output/` and is not source truth.

## Compatibility

This slice changes validation/tooling only. Runtime repository SQL, method signatures, public APIs,
OpenAPI, database schema/migrations, events, Kafka, calculations, dependencies, images, datastores,
and topology are unchanged. The measured 30,000-row latest-position ceiling records the observed
28,500-row representative join shape with narrow deterministic headroom; it does not relax the
sequential-scan or `WindowAgg` prohibition.

## Validation Evidence

- Warning-strict database-evidence unit suite: 35 passed.
- Exact clean-head repository command: 7 PostgreSQL nodes passed in 125.74 seconds; twelve fragments
  assembled with eight passed and four failed report-only scenarios.
- Focused rollback-boundary regression: valuation claim and valuation stale recovery both passed
  against PostgreSQL; the final clean command repeated both proofs in the complete family set.
- Scoped Ruff, formatting, MyPy, and diff hygiene passed.
- Protected PR, exact-main, wiki publication/parity, and final #510 QA evidence remain pending.

## Same-Pattern And Governance Decision

The ledger-page scan is durably routed to #506; the valuation-claim scan is owned by #985; the
distinct valuation stale-selection scan is owned by #987; and the newly measured reprocessing
claim-normalization window scan is owned by deduplicated #988. The subsequent reprocessing claim
and stale recovery meet the representative plan posture. #509 remains closed because identity-first page
hydration and bounded output are intact. #503 retains broader reconciliation streaming, while
#794/#795 retain outbox and Kafka capacity. No runtime defect is hidden or silently repaired inside
the report framework.

The durable lesson is repository-local: representative plan evidence must be exact-source,
production-method based, source-safe, optimizer-flexible, and initially non-certifying. Existing
Lotus backend, CI, review-ledger, and issue-discovery skills already require those behaviors, so no
central skill or platform-context change is needed. The operator wiki changes because the new
command and interpretation are support-visible; publication and strict parity remain post-merge.
