# FX Source Admission And Evidence Integrity

This guide covers the existing operational FX write boundary and native persisted-event identity.
It is not a qualified fixing-window contract or provider certification. The full market/reference
target remains in [RFC-0083](../architecture/RFC-0083-market-reference-data-target-model.md).

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

The current pair/date store is mutable and does not supply a governed immutable fixing revision or
prior-version retrieval. Provider/approved-registry binding, independently observed time, fixing
kind/calendar/version, correction/supersession history, full-window cut, no-look-ahead/conflict
selection and consumer-scoped qualification remain required for the canonical `MarketDataWindow`.
An `UNAVAILABLE` disclosure is not delivery of that target. Instrument reference/suitability
separation and the wider original #458 criteria remain unchanged. #1227 source grants and diagnostic
facts are not upgraded; Performance owns calculations/export contracts and Report owns authoritative
Excel assembly.

## Validation Scope

Owning tests exercise exact-value positive intake, row/batch refusals with no publish/job side
effects, actual registered ASGI routing with in-memory dependencies, native persistence-event
serialization, corrected event identity/replay, and mismatched consumer admission before database
access. These component checks do not establish PostgreSQL retention, supported upstream ingestion,
deployed broker identity or live provider certification. Hosted exact-head and actual-main evidence
remain separate delivery requirements.
