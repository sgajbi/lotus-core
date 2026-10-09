# FX Source Admission And Evidence Integrity

This guide distinguishes legacy global FX writes from canonical tenant/provider/source revision
and sealed-cut custody on the same ingestion, persistence and QCP facilities. Enrollment defaults
to deny-all. Software custody does not approve an institutional provider, certify financial
calculations or close the full [RFC-0083 target](../architecture/RFC-0083-market-reference-data-target-model.md).

| Input/read | Authority | Operator decision |
| --- | --- | --- |
| Legacy `fx_rates` batch | Mutable global pair/date projection; unqualified source | Never infer retained provider history from its timestamp or hash. |
| `fx.source-cut.v1` submission | Verified tenant/principal plus server enrollment/calendar | Configure only independently approved sources; retain one complete cut atomically. |
| QCP `fx_source` selection | Scoped retained revisions, observation and knowledge boundaries | Select explicit provider/source and optional fixed cut; missing authority has no legacy fallback. |

## Supported Operational Input

Send the existing request to `POST /ingest/fx-rates` through the deployment's governed authenticated
ingestion boundary. Currency codes normalize to uppercase; rates remain exact positive finite
`NUMERIC(18,10)` values. The directed pair means units of `to_currency` per one `from_currency`.

```json
{
  "fx_rates": [
    {
      "from_currency": "USD",
      "to_currency": "SGD",
      "rate_date": "2026-07-28",
      "rate": "1.3500000000"
    }
  ]
}
```

HTTP 202 means asynchronous queue acceptance, not completed persistence or analytics qualification.
Unknown fields at either batch or record level return HTTP 422 with `extra_forbidden` before any
job is created or event published. This includes caller provider IDs, observed timestamps,
revision/hash claims, source cuts and calendar versions. Do not strip meaningful custody fields
and then claim the remaining operational write preserves them; route genuine source requirements
to the owning canonical producer contract instead. Never add a consumer-generated hash or timestamp
to manufacture that authority.

## Native Persisted-Event Binding

The existing persistence consumer derives `FxRatePersistedEvent` from its persisted business values
and stages it through the existing outbox. The existing stable hash algorithm binds directed pair,
business date and exact Decimal rate. Observation identity additionally binds `generated_at`, which
is processing generation time. Event admission recomputes both hashes; inconsistent content or
generation time is a validation failure before valuation correction claims or database operations.
Correlation, trace and schema envelope metadata stay outside business identity.

This is consistency validation, not authentication. An internally consistent replacement of content
and both hashes is not independent provider evidence. Existing broker authorization and publisher
custody remain necessary; this change adds no provider approval, signer or distributed transaction.
It preserves existing valid event identities and correction/idempotency behavior.

## Canonical Source Cut Submission

The same `POST /ingest/fx-rates` accepts an alternative `fx.source-cut.v1` body with
`provider_id`, `source_id`, `source_cut_reference`, `source_cut_revision`,
`source_observed_cutoff`, `declared_member_count`, `declared_membership_hash` and `members`.
Each member names `source_record_id`, `source_revision`, directed currencies, `rate_date`, exact
`rate`, `source_observed_at`, `fixing_kind`, `calendar_version` and optional
`predecessor_revision_id`. No caller tenant, enrollment, accepted time, authorization token or
server cut ID is admitted. The typed contract is
[FxSourceCutSubmission](../../src/libs/portfolio-common/portfolio_common/fx_source_events.py).
Its exact domain membership algorithm is
[fx_cut_membership_hash](../../src/libs/portfolio-common/portfolio_common/domain/market_data/fx_source.py);
it is a content check, not independent provider authority.

A cut has 1–512 distinct source records and an encoded event ceiling of 524,288 bytes. The source
cutoff must include every declared member; partial or inconsistent membership is rejected, not
filled from the mutable global table. Admission charges the existing write-rate policy for every
member but creates one asynchronous job and one signed cut command. HTTP 202 `accepted_count=1`
means one cut queued, not all member rows committed or downstream calculations completed.

Verified enterprise principal admission remains mandatory even when ordinary development auth
enforcement is disabled. It requires `ingestion.fx_rates.source_cut.submit`, matching tenant and
service identity, an active server enrollment and its exact server fixing calendar. Registry
configuration is bounded JSON in `LOTUS_FX_SOURCE_ENROLLMENTS`, `LOTUS_FX_SOURCE_CALENDARS` and
`LOTUS_FX_SOURCE_RELAY_KEYS`. Empty registries deny canonical writes. Enrollment binds scope,
principal, currency pairs, validity interval and calendar version. Calendar binds fixing kind,
IANA timezone, local fixing time, publication window, business weekdays and closures; ambiguous or
nonexistent daylight-saving fixing times fail closed. No synthetic provider fixture is deployed
as a real enrollment. Relay secrets are read only from named `LOTUS_FX_SOURCE_RELAY_KEY_*`
environment variables; do not put secrets in registry JSON, public examples or evidence packets.

The existing raw FX topic receives `FxSourceCutReceivedEvent` with a purpose/audience-bound relay
signature over the admitted cut and principal/enrollment/calendar/time claims. The consumer
authenticates before database lookup and requires current admission for fresh writes. Only an
exact committed cut with the original attestation digest can be replayed after grant expiry or
revocation; replay cannot confer authority on changed content or a new attestation. Retain relay
verification keys for the governed replay period.

## Atomic Retention And Historical Selection

The existing persistence consumer owns one outer database transaction for its tenant-aware inbox
fence, `fx_rate_source_cuts`, `fx_rate_source_revisions` and one `FxSourceCutPersistedEvent` outbox
record. No nested savepoint or distributed transaction is introduced. Sorted advisory transaction
locks cover absent roots and current chains; a correction must name the actual current predecessor.
Same version with different content and competing stale corrections refuse without overwriting
history. The database separately fences scope, one root/child, complete exact membership, admission
membership, finite positive NUMERIC values and immutable UPDATE/DELETE. Nonempty TRUNCATE and
downgrade refuse authority loss. PostgreSQL `clock_timestamp()` determines Core acceptance; source
observation time is never substituted for that knowledge boundary.

The existing QCP benchmark market-series request accepts optional `fx_source` with explicit
`provider_id`, `source_id`, inclusive `source_as_of`, inclusive `known_as_of` and optional retained
`cut_id`. Canonical reads require verified enterprise tenant context. A source fact observed later
than `source_as_of`, or admitted later than `known_as_of`, is invisible. A correction unknown at the
knowledge instant cannot hide its parent. Fixed cuts resolve exact retained members and remain
stable after later corrections. Multiple independent chains for the selected pair/date are an
explicit conflict, not a caller-timestamp ranking or last-write-wins choice. Other providers are
never silently substituted. Responses distinguish `RETAINED_SOURCE`, `LEGACY_UNQUALIFIED`,
`UNAVAILABLE`, identity conversion and not-requested posture, with actual retained revision hashes,
calendar, observed time, accepted time and cut provenance.

The persisted-cut notification is verified against its retained row by the existing valuation
consumer before notification fencing. It does **not** rewrite global legacy rates or enqueue
tenantless valuation corrections. Financial consumers must explicitly adopt the retained source
read contract; the presence of a notification does not prove that adoption or financial completion.

## Deployment And Rollback

1. Apply migration `c179b2c3d540` after `c178b2c3d539`; legacy rates and pending v1 jobs are preserved,
   not backfilled into qualified source history.
2. Deploy explicit canonical variants at both existing FX consumers before admitting a canonical
   producer. Old consumers cannot safely interpret the new typed variant.
3. Keep canonical enrollment empty until independently approved configuration and downstream
   compatibility are established. Legacy v1 writes continue unchanged and unqualified.
4. When retained authority exists, use forward fix or independently governed restore. Downgrade is
   supported only when both authority tables are empty, under an exclusive lock and READ COMMITTED
   transaction; it never erases retained source history to make an older binary start.

## Operator Response

| Observation | Response | Not established |
| --- | --- | --- |
| HTTP 422 unknown custody field | Correct the supported request contract; escalate required source custody to its owner. | Provider facts were retained or approved. |
| Persisted-event identity mismatch | Preserve original event and validation failure; investigate publisher/payload mismatch through existing DLQ/recovery controls. | A safe replay or permission to rewrite hashes. |
| Valid native event | Use its exact source-owned business and observation identities for the existing correction workflow. | Qualified provider fixing or retained prior revision. |

Do not rewrite a mismatched event's hashes merely to make it pass, bypass admission or rerun an
unchanged producer blindly. Preserve failure receipts and use the existing authorized replay and
incident procedures. Legacy synthetic events with placeholder hashes are invalid evidence; native
events emitted by `from_observation` retain their original algorithm and valid wire compatibility.

## Remaining Original Acceptance

The legacy pair/date store remains mutable and unqualified. Canonical software retention and
selection do not replace independent provider approval, genuine observations, complete enrolled
fixing coverage, deployed producer/consumer qualification or full-window financial acceptance.
An `UNAVAILABLE` disclosure is not delivery of that target. Instrument reference/suitability
separation and the wider original #458 criteria remain unchanged. #1227 source grants and diagnostic
facts are not upgraded; Performance owns calculations/export contracts and Report owns authoritative
Excel assembly.

## Validation Scope

Component tests exercise signed admission/refusal, exact bounded membership, calendar rules,
expired replay, typed notification and QCP provenance refusals. Registered PostgreSQL controls in
`test_fx_source_cut_postgresql.py` and `test_fx_rate_source_revision_postgresql.py` cover actual
HTTP/job/inbox/cut/revision/outbox effects, rollback after flush, actual overlapping advisory lock,
historical boundaries, conflict and downgrade controls. They run in the native critical DB and query
authority DB suites. Their captured publisher transport is not live Kafka delivery, institutional
approval or upstream worker certification. Require actual successful producing receipts before
using a registered test as passed evidence; selectors alone prove neither execution nor acceptance.
Hosted exact-head, actual-main and broader financial/live evidence remain separate requirements.

The migration compatibility control retains populated legacy rates and both accepted and queued
legacy jobs byte-for-byte across empty-authority downgrade/upgrade. It then invokes the registered
legacy consumer with an in-transit v1 event, requiring only legacy FX/inbox/outbox effects and no
canonical revisions or cut. This does not claim that a queued job reached worker completion.
