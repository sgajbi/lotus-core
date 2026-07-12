# CR-1451: Canonical Booked Transaction Replay Adapter

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Objective

Implement the replay application port with explicit infrastructure ownership while reusing the
canonical Core replay repository and publication semantics.

## Change

Added `SqlAlchemyBookedTransactionReplayAdapter`, which:

- creates one short-lived SQLAlchemy session per replay request;
- constructs a canonical transaction replayer through an injected infrastructure factory;
- requests replay for exactly one normalized transaction id;
- propagates correlation id explicitly;
- maps canonical replay counts `0` and `1` to application booleans;
- raises an explicit invariant violation for an impossible count above one;
- closes the session on success and failure through the async context boundary.

The adapter depends on a narrow `CanonicalTransactionReplayer` protocol rather than making the
application layer import `ReprocessingRepository`.

CR-1453 subsequently promoted replay dependency and invariant errors to application-owned error
types so delivery does not depend on infrastructure exceptions.

## Compatibility

No topic, group, payload, ordering, correlation, retry, partial-publish, flush, DLQ, runtime, image,
schema, or public API behavior changed. Production composition and delivery are not registered yet.

## Validation

- replayed/not-found, delegation, correlation, session lifecycle, and cardinality tests: 3 passed;
- focused MyPy and Ruff passed;
- in-process boundary and diff checks passed.

No README/wiki change is required because deployed replay behavior and topology are unchanged.
