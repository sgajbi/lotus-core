# CR-1656: Deterministic Ingestion Replay Outcomes

## Scope

This review owns GitHub issue #833 and the same-pattern inventory of job-backed ingestion command
paths. It covers reference-data persistence, publish-backed batch and portfolio-bundle commands,
business-date ingestion, transaction reprocessing's pre-resolution lookup, and post-work
bookkeeping failures.

## Finding

An existing idempotency job was treated as a successful duplicate without considering its durable
lifecycle state. A client that lost a persistence conflict, Kafka failure, partial publication, or
bookkeeping-failure response could retry the same request and receive a false `202`. Reprocessing
could do this before resolving current source identity, which concealed the failure and bypassed
the source lookup without reproducing the original outcome.

The persistence schema stored failure reason and phase but did not retain the stable HTTP status,
application code, source-safe detail, or safe headers required to reproduce a client-visible
outcome. PostgreSQL proof also found that the initial completeness check needed an explicit
non-null status predicate to avoid SQL three-valued-logic acceptance of code/detail/header-only
partial evidence.

Late review also found that job-backed duplicates were initially resolved after write-mode and
rate-limit controls. A lost-response retry could therefore return a new `429` when the original
request or later traffic exhausted the budget, even though no new work would be performed.

## Decision

- `resolve_ingestion_idempotency_replay(...)` is the pure application policy. It accepts only a
  replay-safe queued job, reproduces durable failures, returns
  `409 INGESTION_REQUEST_IN_PROGRESS` for unresolved accepted jobs, and fails closed for unknown
  or incomplete legacy state.
- Durable outcomes comprise status, stable code, source-safe detail, and optional safe headers.
  Retry/requeue transitions clear stale outcome fields.
- Publish and bookkeeping response builders are application-owned. Routers adapt stored outcomes
  and do not rebuild competing payloads.
- The non-reserving reprocessing replay reader returns lifecycle outcome evidence, allowing a
  matching failed request to reproduce its result before source resolution without republishing.
- The same non-reserving reader is applied across every job-backed command before write-mode,
  reprocessing-permission, and rate-limit controls. Established same-payload outcomes do not consume
  new write budget; unmatched or divergent requests retain the normal controls and atomic
  create/conflict path.
- The single-transaction endpoint remains intentionally jobless and does not claim job-backed
  deterministic replay.

## Compatibility and operational impact

Queued duplicates retain the existing `202` acknowledgement and do not repeat work. Failed or
unresolved duplicates intentionally stop returning false success: durable failures reproduce their
original 4xx/5xx outcome, and unresolved accepted jobs return a typed 409. Same-key/different-payload
conflicts remain `INGESTION_IDEMPOTENCY_CONFLICT`.

Migration `c121b2c3d4fa` adds four nullable columns and a `NOT VALID` completeness constraint before
validation, avoiding a retained-row rewrite while rejecting partial new outcomes. Existing rows
remain valid with all four fields null. Operators must use the returned job identity and governed
bookkeeping recovery rather than blindly resubmitting completed work.

## Pattern inventory

Corrected in scope:

- shared reference-data registry handler;
- transaction, portfolio, instrument, market-price, FX-rate, and reprocessing batch commands;
- portfolio-bundle command;
- business-date command;
- reprocessing pre-resolution replay lookup;
- post-persist and post-publish bookkeeping outcomes.

Audited without change:

- single-transaction ingestion has no durable job lifecycle;
- upload commit delegates to the governed batch path;
- ingestion retry and consumer-DLQ replay use separate audited replay workflows and stable outcome
  contracts.

## Evidence

- warning-strict application, lifecycle, migration, handler, route, and OpenAPI tests;
- lost-response endpoint proofs for reference persistence, authority conflict, Kafka failure,
  partial bundle publication, business-date publication, reprocessing partial publication, and
  post-publish/post-persist bookkeeping;
- handler proofs that durable batch, reference-data, business-date, and reprocessing replays bypass
  new-write controls while unmatched requests retain their existing policy sequence;
- PostgreSQL apply/downgrade/reapply proof including completeness, normalization, status range, and
  constraint validation;
- signed slice commits and exact validation evidence recorded on issue #833 and the delivery PR.
