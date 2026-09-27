# Shared Requirement: Idempotency, Replay, and Reprocessing

## Purpose

Define safe processing behavior for repeated, replayed, or rebuilt transactions.

## Required Concepts

Every transaction RFC must define:

- idempotency key
- replay behavior
- duplicate detection behavior
- reprocessing behavior
- conflict behavior for same business event with inconsistent payload

## Rule

Reprocessing the same transaction under the same policy and same input must be deterministic.

## Conflict Handling

If the same transaction id or same economic event arrives with materially different payload, the RFC must define whether to:

- reject
- park
- replace under approved correction flow
- escalate as reconciliation conflict

## Raw-Ledger Source Transaction Fence

The persistence boundary treats `(tenant_id, transaction_id)` as the semantic replay key and stores
a versioned SHA-256 fingerprint of the authoritative economic payload on the durable transaction
row. Transport observations such as correlation id, event creation time, and replay epoch are not
economic inputs. Processor-derived state is also excluded because it has its own source and replay
authority.

An identical source payload is an idempotent no-op. A materially changed payload for an existing
source transaction fails closed with `TRANSACTION_SEMANTIC_CONFLICT`, even if transient
`processed_events` retention has expired. The conflict must leave the transaction and its named fee
components unchanged. Do not delete the durable transaction, rewrite its fingerprint, or purge the
semantic fence to force acceptance.

This fence does not grant correction authority. A bank-approved correction or cancellation remains
the responsibility of its governed correction contract and must establish a new, explicit source
fact transition rather than using ordinary replay to replace history.

This is a bounded first slice of issue #473. The current ledger still uses a globally unique
transaction id, so a foreign-tenant replay of that id fails closed under the existing #798 policy;
this slice does not introduce a composite transaction key. Keep #473 open for the remaining
integration and recovery closure.
