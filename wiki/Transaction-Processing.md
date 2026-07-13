# Transaction Processing

`portfolio_transaction_processing_service` is the single runtime owner for atomic cost, cashflow,
and position mutation after a transaction is persisted. It keeps those financial policies
modular while sharing one transaction boundary, idempotency decision, and compatibility outbox.

## Processing Flow

1. The live or replay-request consumer receives the existing governed transaction event.
2. Infrastructure maps the event DTO to immutable `BookedTransaction` domain data.
3. The application use case coordinates cost, cashflow, and position modules through ports.
4. Domain policies calculate state changes without importing Pydantic, SQLAlchemy, Kafka, metrics,
   or repository implementations.
5. Infrastructure adapters persist all changes and compatibility outbox events in one database
   unit of work.
6. A failure rolls back the combined state transition; replay uses the same application path.

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

The validation functions currently provide contract-conformance evidence. This ownership move did
not activate new runtime rejection behavior. Any future validation cutover requires an intentional
behavior decision, compatibility review, tests, and contract documentation.

## Shared-Library Boundary

`portfolio_common.transaction_domain` does not own ordinary BUY, SELL, DIVIDEND, or INTEREST models
or policy facades. It retains corporate-action, FX, and effective-processing compatibility only
until each responsibility has an independently evidenced target owner. Do not recreate deleted
ordinary transaction modules in the shared package or retired calculator source roots.

## Extension Rule

For a new transaction type:

1. model the economic facts in domain language without framework objects,
2. place reusable ordinary booking or settlement policy under `app/domain/transaction`,
3. keep cost, cashflow, and position calculations in their distinct domain modules,
4. map transport and persistence representations at infrastructure boundaries,
5. add lifecycle, replay, idempotency, dual-leg, and rollback tests before runtime activation.

## Compatibility

The consolidation preserves public APIs, OpenAPI, event fields and versions, topic names, database
schema, generated product/cash event ordering, and downstream responses. It changes internal code
ownership and removes duplicate extension points.

## Evidence

- [Architecture](Architecture)
- [Cost Processing](Cost-Calculator)
- [Cashflow Calculator](Cashflow-Calculator)
- [Position Processing](Position-Calculator)
- [Validation and CI](Validation-and-CI)
