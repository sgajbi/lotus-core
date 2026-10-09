# Portfolio Financial Source Observations

`PortfolioFinancialSourceObservations` v1 exposes independent immutable producer facts, not
portfolio eligibility, funding policy or a composite readiness decision. Core provides the
admission and historical-read structure. No institutionally qualified producer is configured;
authoritative consumption and joined-cut compatibility remain `UNAVAILABLE`.

## Ownership and supported boundaries

| Family | Producer-owned facts | Core must not infer |
| --- | --- | --- |
| Cash availability | Nullable settled, encumbered and available exact amounts, currency and declared coverage | A settled-minus-reserve formula, FX aggregation or available cash from valuation |
| Funding/investment | Independent nullable funded and invested assertions | Flags from ACTIVE lifecycle, first booking, mandate membership or positive valuation |

Observed zero and false are facts; null is absence. Negative finite cash values are not silently
clipped. Decimal amounts are persisted as unbounded exact PostgreSQL numeric values with finite
checks, without float conversion or scale rounding. Each family retains its own definition,
producer record/revision, source cut, business interval, observed/generated timestamps and
server receipt. Manage is one consumer; it does not own the reusable source product.

Cash facts canonicalize only representations that PostgreSQL NUMERIC cannot retain: zero has
no negative sign, and positive exponents expand into exact fixed-point digits before hashing
and admission. Fractional display scale and trailing digits remain significant; `0.00` is not
rewritten as `0`. Nonzero sign and precision are unchanged, regardless of ambient Decimal
precision. The shared calculation-lineage hash is unchanged. This does not repair or rewrite
previously stored contradictory hashes, which continue to fail closed.
The cash boundary checks NUMERIC's 131072 integer-digit and 16383 fractional-digit limits
before any positive-exponent expansion; negative exponents are retained without expansion.
An existing source revision replays only when its reconstructed, validated content hash
matches the submitted content hash. Numerical equality alone is insufficient: changing
`1.00` to `1.0` or `0.00` to `0` under a new receipt is divergent replay and rolls back the
new receipt without changing immutable facts or scoped heads.

## Admission and terminal receipt

The two registered write commands are:

- `POST /ingest/portfolio-cash-availability-observations`
- `POST /ingest/portfolio-funding-investment-observations`

Both require `X-Idempotency-Key`, signed verified tenant/service identity, the exact family's
ingestion write capability and an explicit server-owned tenant/portfolio/producer/family grant.
The default grant collection is empty. A source-data read capability is not a write permission.
Producer permission is not institutional qualification: even an explicitly admitted producer is
recorded as `unqualified`. Request bodies cannot supply tenant identity, approval, qualification
or `quality_status`. Public `source_system` and `source_version` map explicitly to the stored
producer identity and revision; no aliases are accepted.

The native job creation transaction stages the typed fact, scoped head and receipt together.
Only after append/CAS succeeds may its supplied-session creation callback transition its newly
attached observation receipt from `accepted` to `completed`, with a server completion timestamp.
The enclosing transaction publishes them atomically. Successful admission returns HTTP 200 and
the persisted completed receipt; it does not claim queued worker processing. Failures roll back
the new receipt and facts. Completion is unavailable to existing, foreign, detached, failed or
asynchronous jobs. Existing async command families retain their prior lifecycle.

Job evidence is restricted and fingerprint-only: no replayable payload, partial replay or TTL
is retained. Exact idempotent returns skip the creation callback. A divergent payload under the
same endpoint/key refuses. Exact fact replay under another admitted request does not create a
second fact or rewind a corrected head. Completed receipts are terminal, excluded from
stalled/backlog selectors and queue/failure/retry transitions, and readable through the native
job detail/list contracts. There is no source event/outbox dispatch in this product; local
financial PostgreSQL ACID remains the boundary, not XA/2PC.

After verified producer, family capability and tenant admission, an exact fingerprint replay
returns only a completed receipt with its completion timestamp. It bypasses new-write mode and
rate controls; an incomplete receipt cannot be reported as success. Completed record counts are
included in ingestion processed throughput, while accepted records remain backlog and queued or
failed record accounting retains its existing meaning. Synchronous completed receipts keep their
completion timestamps but do not enter asynchronous queue-latency samples in either the native
PostgreSQL aggregate or the fallback. Fast synchronous work cannot dilute a slow queue's p95.
SLO total/failed counts and current/previous error-budget windows use only the asynchronous
cohort, excluding `completed` receipts. Synchronous successes cannot dilute asynchronous failure
rates or inflate remaining error budget; failed admission leaves no failed synchronous receipt.
Existing percentile algorithms, thresholds, backlog and DLQ semantics remain unchanged.
The shared ingestion/event-replay job list and detail status schema includes `completed` for
readable terminal receipt evidence; this does not add asynchronous processing or replay authority.

Authority intervals are half-open. A null upper bound is unbounded, not a finite maximum-date
sentinel; even an open interval beginning on the maximum supported date competes with another
open interval in the same authority scope. Finite touching intervals do not overlap. The bounded
actual `c178` descent and concurrent downgrade/TRUNCATE refusal proofs also execute in
`critical-db-coverage`; suite routing alone is not PostgreSQL execution evidence.

## Immutable history and authority keys

The source revision key is tenant, portfolio, producer, family and producer record. First
revision is 1. A correction must name the current predecessor ID/hash and increment the exact
revision by one; foreign predecessor, divergent same revision and stale CAS refuse. Coverage
scope and cash currency cannot change within a record's correction chain.

Competing interval admission is serialized separately by tenant, portfolio, producer, family,
declared coverage scope and, for cash, currency. Different declared scopes or currencies can
progress independently; contradictory overlapping current records in the same declared
authority key refuse. A different scope name does not prove economic non-overlap or qualify
authority. No cross-scope total or currency conversion is produced. Sorted transaction-scoped
source/authority locks protect same-record races and reversed batches without a global lock.

Facts cannot be updated or deleted. A distinct PostgreSQL TRUNCATE guard permits only empty
fact/head tables under READ COMMITTED, after ACCESS EXCLUSIVE locking, and refuses populated
tables or transaction-fixed isolation snapshots. This preserves empty fixture cascades without
an immutability bypass; a parent CASCADE cannot destroy retained history.
Only the narrow head projection changes through admitted correction. Migration
`c178b2c3d539` starts with empty tables and no qualifying backfill. Downgrade locks all four
owned tables in deterministic order before any emptiness check, then refuses nonempty history.
Operators must restore or forward-fix retained history, not disable guards or delete facts.

## Historical read contract

`POST /integration/portfolios/{portfolio_id}/financial-source-observations/query` is an Analytics
Input product protected by tenant scope and its source-data read capability. The request has
one business `as_of_date` and independent family selectors:

- Original/corrected pin: producer record identity plus observation ID, content hash, source cut
  and source revision are all required.
- Latest: explicit `latest_restated=true` and producer record identity, without mixed pins.
- Missing selector: unavailable; never implicit latest.

One PostgreSQL statement reads both families from the same statement snapshot. Original pins
read immutable facts without joining mutable heads and remain readable after correction or
session recreation. Latest selection joins the scoped current head and is labelled restated.
The effective interval is half-open: start inclusive, end exclusive. Observation and receipt
time do not replace the business date; late-observed historical facts remain attributable.

Returned facts are diagnostic and independently attributed. Missing/partial coverage,
unqualified producer, mismatched scope/pin or missing evidence cannot establish authoritative
availability. The response has no combined authoritative source cut. Date equality alone does
not establish compatibility with valuation, cashflow or another product. Existing composite,
prior-lineage, transition-preimage and live financial qualification gaps are not closed by this
product or by candidate unit/CI evidence.

Generic metadata agrees with this posture: `data_quality_status`, `freshness_status` and
`degradation.status` are `UNAVAILABLE`. The degradation summary contains the deduplicated bounded
response reasons, with product-level qualification/compatibility details and family-level
unavailable, scope, business-date, evidence, pin or coverage details. Diagnostic facts remain
attributed evidence, including observed zero and false values; null remains unknown. Degradation
does not replace those facts with defaults or qualify their use. Its details do not substitute
the request date or serving timestamp for missing authoritative source-time evidence.

## Per-Fact Verification Receipt

The existing ingestion records optionally carry `verification_receipt`, a signed
`PortfolioSourceFactVerificationReceipt` v1 with purpose `PORTFOLIO_FINANCIAL_SOURCE_FACT`.
This is distinct from producer submission permission, FX custody and Manage's
`COMPOSITE_MONTHLY_SOURCE_CUT` approval. An absent receipt preserves the original request
serialization and idempotency fingerprint; it never upgrades old facts by backfill.

Core registers trusted verifier keys and complete cut manifests independently of the caller.
`LOTUS_PORTFOLIO_FACT_VERIFICATION_KEYS` and `LOTUS_PORTFOLIO_FACT_VERIFICATION_CUTS` are bounded
JSON arrays, empty by default. Each key binds issuer/key identity, trusted consumer, tenant,
portfolio, producer, family, currency, definition and coverage scope, with aware validity and
optional revocation instants. Key material comes only from its named
`LOTUS_PORTFOLIO_FACT_VERIFICATION_KEY_*` secret environment variable. Each cut registration
binds that same scope, exact producer cut ID and independent manifest digest. A submitted
signed digest cannot register its own authority. Invalid configuration refuses safely; never
log registry secrets or signed payloads.

Receipt verification binds the original typed fact hash and complete envelope, including revision,
business interval, observed/generated time, coverage and cut; it also binds consumer, currency,
business date and manifest digest. HMAC authentication, exact purpose, current expiry/revocation
and complete coverage are required. The native supplied ingestion transaction writes the original
fact, scoped head, append-only receipt linkage and terminal job together. Failed verification
rolls everything back. `c181b2c3d542` follows `c179b2c3d540`; it adds only receipt storage with
family-specific original-fact foreign keys. UPDATE, DELETE and TRUNCATE refuse, and downgrade
refuses populated receipts. Existing original economic rows and B's index migration are unchanged.

The existing QCP query returns a receipt only after re-verifying it for the authenticated
service consumer at read time. When every requested family has a valid selected fact and current
receipt, `fact_verification_status` is `FACT_VERIFIED`; otherwise all selected receipt projections
are suppressed. Missing verification fields are omitted from the legacy wire representation.
Original fact hashes, revisions and nullable amounts/flags are unchanged. Provider qualification,
`authoritative_state`, joined-cut compatibility and generic availability metadata remain unavailable.
Manage and Performance must independently verify the receipt and complete assembly; a single fact
receipt is not a positive five-input monthly financial decision, retained-history proof or live
processing-completion evidence.

The owning `test_portfolio_source_verification_postgresql.py` controls use only the native
DB-only `query-authority-db-contract` scope and a capability-validated owned schema. They exercise
new-session receipt recovery/current revocation, native job/fact rollback, mutation barriers,
populated downgrade refusal and empty downgrade/upgrade preserving original facts. Synthetic
signing keys prove software behavior only; current issuer enrollment and genuine producer evidence
remain independent acceptance requirements.

## Verification and evidence limits

Focused tests cover exact DTOs, independent flags/amounts, default-deny admission, registered
routes, native creation callback/replay/rollback control flow, original pins and explicit
restatement. Simulated SQL tests are not PostgreSQL ACID, application-name, cross-loop or live
financial proof. Owning PostgreSQL suites must prove persisted terminal receipts, exact replay,
concurrent CAS/authority-key barriers, rollback, original/corrected readback, immutable SQL
refusals and the concurrent downgrade/admission fence against an isolated authorized database.
Their native execution evidence, not collection or suite membership alone, is required for
acceptance. Exact-main release and publication are separate promotion responsibilities.
