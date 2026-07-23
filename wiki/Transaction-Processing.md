# Transaction Processing

`portfolio_transaction_processing_service` is the single runtime owner for atomic cost, cashflow,
and position mutation after a transaction is persisted. It keeps those financial policies
modular while sharing one transaction boundary, idempotency decision, and compatibility outbox.
Current scope is the implemented combined transaction worker and its service-owned ordinary
transaction domain; valuation, timeseries, and downstream analytics remain separate capabilities.

## Processing Flow

1. The live or replay-request consumer receives the existing governed transaction event.
2. Infrastructure maps the event DTO to immutable `BookedTransaction` domain data.
3. The application use case coordinates cost, cashflow, and position modules through ports.
4. Domain policies calculate state changes without importing Pydantic, SQLAlchemy, Kafka, metrics,
   or repository implementations.
5. Infrastructure adapters persist all changes and compatibility outbox events in one database
   unit of work.
6. A failure rolls back the combined state transition; replay uses the same application path.

The combined unit of work owns session lifecycle and adapter composition only. Transaction claim
persistence, the stable processing service identity, and physical/semantic outcome translation live
under `app/infrastructure/idempotency`; application orchestration consumes them only through
`TransactionIdempotencyPort`. Do not add concrete claim repository behavior back to the unit of
work or expose the adapter through the broad infrastructure package root.

The concrete atomic boundary is
`app/infrastructure/transaction_processing/unit_of_work.py`. It composes cost, cashflow, position,
readiness, idempotency, and outbox adapters over one SQLAlchemy session and one commit. The class is
not exported from the broad infrastructure root; runtime builders obtain it through the aggregate
transaction-processing package.

Concrete use-case builders live at `app/runtime/dependency_composition.py`. The live/replay consumer
composition and the AVCO reconciliation operator command import this explicit composition root;
infrastructure packages expose adapters, not application assembly functions.

The `app/infrastructure` root is namespace-only. Runtime code and tests import adapters through
their named capability packages so cashflow, cost basis, position, idempotency, mapping, processing,
readiness, and replay ownership remains visible in every dependency.

The event anti-corruption boundary is `app/infrastructure/transaction_mapping`. Its
`booked_transaction` mapper preserves all governed envelope and domain fields in both directions;
its `foreign_exchange_instrument` mapper translates synthetic FX contract domain values to the
governed instrument event. Domain and application modules remain independent of Pydantic event
models, and new transaction event translations belong in this package rather than flat
infrastructure files.

Booked-transaction replay remains a separate application use case because operator replay has
different backlog, recovery, and delivery controls. Its infrastructure adapter lives under
`app/infrastructure/transaction_replay`, opens a short-lived SQLAlchemy session, delegates to the
canonical publisher, maps dependency failures, and enforces that one transaction ID publishes zero
or one record. Delivery code owns retry and DLQ handling; replay infrastructure is not exported from
the broad infrastructure package root.

Aggregate live and replay stage telemetry is an infrastructure adapter under
`app/infrastructure/transaction_processing`. It implements the application observer port and keeps
Prometheus counters, histograms, clocks, and telemetry-failure containment outside application and
domain code. The adapter is not a broad infrastructure-root export, and metric names, bounded stage
and outcome labels, and failure behavior remain operational contracts.

## Ordinary Transaction Domain

The service-owned `app/domain/transaction` package owns ordinary BUY, SELL, DIVIDEND, and INTEREST:

- booking metadata and stable policy identifiers,
- validation findings and reason-code values,
- cash-entry mode policy,
- generated settlement cash-leg economics and linkage,
- upstream-provided product/cash-leg pairing.

These policies consume `BookedTransaction`. Existing event envelopes are mapped only in
infrastructure, where schema version, event type, correlation, trace, and other governed metadata
must be preserved.

Most validation functions remain contract-conformance evidence. The one active settlement boundary
is non-positive proceeds after resolved fees for SELL, DIVIDEND, and INTEREST income. The application
classifies physical and semantic idempotency inside the combined unit of work first, then rejects a
newly claimed or repair delivery before cost, position, cashflow, or commit. Harmless historical
duplicates remain acknowledgements. Other strict-metadata validators remain conformance-only until
an intentional behavior decision, compatibility review, tests, and contract documentation activate
them.

## Ordinary Settlement Cash

One transaction-domain policy resolves fee precedence, signed cash amount, and ledger direction:

| Transaction | Signed settlement cash |
| --- | --- |
| BUY | `-(gross amount + resolved fee)` |
| SELL | `gross proceeds - resolved fee` |
| DIVIDEND | `gross dividend - source-recorded withholding - resolved fee` |
| INTEREST income | `pre-fee net interest - resolved fee` |
| INTEREST expense | `-(pre-fee net interest + resolved fee)` |

Component fee fields take precedence over aggregate `trade_fee` when any component is present.
SELL, DIVIDEND, and INTEREST income must remain strictly positive before the inflow sign is applied.
Zero or negative proceeds are non-retryable hard rejections with stable family codes; absolute-value
normalization must never turn invalid proceeds into an apparent inflow. Generated settlement legs
and persisted product cashflows consume the same policy result.

For current DIVIDEND booking, the existing nullable `withholding_tax_amount` is preserved as
separate ledger/query evidence and reduces available settlement proceeds before the fee. Negative
withholding, withholding above gross, or non-positive resulting cash fails closed with stable
`DIVIDEND_014`, `DIVIDEND_015`, or `DIVIDEND_013` reason codes. Null and zero withholding preserve
the prior gross-minus-fee result. Every output produced by current cost processing retains
current-booking economics when it participates in an inline rebuild, including transformed or
split identities. Previously accepted suffix rows receive the explicit historical-rebuild context,
but source-recorded positive DIVIDEND withholding remains in product-cashflow economics so rebuilt
product and generated cash legs stay reconciled. Null/zero withholding and rows that predate the
current settlement fences retain legacy arithmetic.
Withholding-rate derivation, other receipt deductions, a supplied-net identity, return-of-capital,
basis reduction, and advanced timing remain tracked under #448.

FX fees and taxes use a separate-linked-posting policy. A non-zero aggregate or component fee on an
FX spot, forward, swap, or generated cash-settlement leg fails before booking, cost mutation, or
cashflow sign normalization with `FX_025_NON_ZERO_EMBEDDED_FEE`. Absent and zero inline fees retain
existing economics. Book supported charges as distinct `FEE`/`TAX` transactions carrying the same
`economic_event_id` and `linked_transaction_group_id`; do not infer fee currency or charged-leg
ownership from either FX cash leg.

## INTEREST Settlement Economics

For INTEREST, `net_interest_amount` is after withholding tax and other interest deductions but
before separately reported transaction fees. One domain policy now owns reconciliation, generated
cash-leg, and persisted cashflow arithmetic:

| Direction | Settlement cash magnitude |
| --- | --- |
| `INCOME` | `net_interest_amount - transaction_fee` |
| `EXPENSE` | `net_interest_amount + transaction_fee` |

Cashflow sign records the income inflow or expense outflow. An explicit conforming net amount and
the equivalent derived net amount must produce the same settlement cash. This corrected the prior
fee-bearing source-shape difference; it did not rename fields, reason codes, events, or database
columns. Downstream consumers needing settled cash should use the linked cashflow amount rather than
treating `net_interest_amount` as fee-inclusive cash.

For a current booking, an explicit pre-fee net that does not reconcile to gross interest less
withholding and other deductions is rejected with
`INTEREST_015_NET_RECONCILIATION_MISMATCH` after idempotency classification and before financial
writes. Historical rows already accepted before this active boundary retain their pre-policy
economics only when Core supplies them through the explicit position-history rebuild context.

## Shared-Library Boundary

`portfolio_common.transaction_domain` is retired. Ordinary settlement, corporate-action, FX, and
effective-processing policies are owned by the unified transaction-processing domain. Shared
libraries retain only owner-neutral event contracts, controlled vocabularies, normalization, and
infrastructure support. Do not recreate transaction policy facades in the shared package or the
retired calculator source roots. FX canonical values are immutable and framework-independent;
transport events are mapped at delivery and infrastructure boundaries.

## Extension Rule

For a new transaction type:

1. model the economic facts in domain language without framework objects,
2. place reusable ordinary booking or settlement policy under `app/domain/transaction`,
3. keep cost, cashflow, and position calculations in their distinct domain modules,
4. map transport and persistence representations at infrastructure boundaries,
5. add lifecycle, replay, idempotency, dual-leg, and rollback tests before runtime activation.

## Compatibility

The consolidation preserves public field names, event versions, topic names, database schema,
generated product/cash event ordering, and downstream response shapes. Current-booking DIVIDEND
cash intentionally changes only when the existing withholding field is non-zero; null/zero
withholding preserves prior behavior. INTEREST fee-bearing settlement arithmetic and rejection of
fee-equal or fee-dominated SELL, DIVIDEND, and INTEREST income remain documented intentional
behavior corrections.

## Evidence

- [Architecture](Architecture)
- [Cost Processing](Cost-Calculator)
- [Cashflow Calculator](Cashflow-Calculator)
- [Position Processing](Position-Calculator)
- [Validation and CI](Validation-and-CI)
