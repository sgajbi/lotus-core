# Portfolio Financial Flow Observations

`PortfolioFinancialFlowObservations` v1 retains explicitly declared flow events and complete
producer/window manifests for `lotus-manage`. It does not book transactions, calculate cashflows,
qualify a producer or approve a monthly assembly. Independent whole-assembly verification remains
downstream. Legacy data without these declarations remains unavailable. Owning PostgreSQL,
registered HTTP and restart/source-withdrawal validation remain required before runtime support
is established; source/unit evidence alone does not establish that support.

## Declarations And Actual Receipt

| Field | Required source meaning |
| --- | --- |
| `source_record_id` | Stable producer event ID, mapped explicitly to private `source_record_id` storage. Never generated from amount/date/hash. |
| `flow_source_record_revision` | Positive contiguous revision of this producer event, mapped to private `source_revision`. It is distinct from a source contract/product version. |
| `business_date` | Declared date inside the effective interval. |
| `currency`, `amount` | Uppercase three-letter currency and finite exact Decimal text. No rounding, sign or FX inference. |
| `classification` | `EXTERNAL_CASH`, `INTERNAL_TRANSFER`, `REVERSAL` or `IN_KIND`. |
| `posting_state` | Required `POSTED`, `CANCELLED` or `UNKNOWN`; never defaulted. |
| `reversal_state`, `reverses_source_record_id`, `reversal_target` | Required declaration, stable target ID and nullable exact target pin containing event/observation/hash/version. NONE and UNKNOWN require explicit null target pins. REVERSES requires REVERSAL classification and a retained immutable same-scope target. UNKNOWN is unavailable. |
| `economic_event_id`, `transaction_id` | Optional exact existing references. Supplied references must match tenant, portfolio, producer and source record. |
| `received_at`, `receipt_job_id` | Server-only evidence, forbidden in producer input. |

Pins and revision paths use `source_record_id` and `flow_source_record_revision`; reversal references use
`reverses_source_record_id` and an exact dedicated target pin. The unreleased names `event_id`, `source_version`, `source_event_id`,
`source_event_version` and `reverses_source_event_id` are not accepted as aliases. Existing main APIs and supplier payload bytes retain
their meanings. Private SQL `reverses_event_id` remains an explicitly mapped storage column.

The admitted HTTP handler captures aware UTC time for the first successful immutable revision.
It is Core's first admitted ingress, not socket arrival or historic bank receipt. January business
events admitted in October retain October receipt time. Exact idempotency replay returns the
original job. Re-submitting the same fact cannot overwrite its first receipt/time. Corrections
require contiguous revision plus exact predecessor/head CAS and receive their own current receipt;
original evidence remains retrievable. Cancellation is a corrected declaration; reversal is a
distinct event. Neither changes economic ledger rows.

Amounts reuse the existing exact NUMERIC observation policy, including zero and positive exponent
canonicalization. Fractional scale remains significant to the typed hash. Missing amounts, floats,
nonfinite values and unrepresentable exponents refuse admission.

## Native Sequence

1. Submit `POST /ingest/portfolio-flow-event-observations` with `observations` and
   `X-Idempotency-Key`. The existing synchronous path commits receipt, facts and heads in one
   local transaction; content hashes are validated against the admitted tenant.
2. Acquire retained pins through
   `GET /integration/financial-source-observations/flow-events/versions/{flow_source_record_revision}`.
   Required query parameters `portfolio_id`, `source_system` and `source_record_id` carry the exact opaque
   identities. Original/corrected revisions are independently selectable without implicit latest selection.
3. Submit `POST /ingest/portfolio-flow-source-cuts` with exactly one item in `cuts` and a new
   idempotency key. Ordered `event_pins` contain in-window event/observation/hash/version identities;
   required `dependency_pins` separately name the complete retained reversal dependency closure,
   explicitly empty when unnecessary. `producer_manifest_hash` is recomputed against the admitted
   tenant. Empty manifests still require a valid own receipt. A reversal submission must first
   acquire the target's actual immutable pins through the revision lookup operation.
4. Read `POST /integration/financial-source-observations/flow-events/query`
   with required opaque query parameter `portfolio_id` and the unchanged strict request body:
   exact source/cut/revision/manifest hash, currency, inclusive `window` and bounded `page`.

Each stage is independently atomic/idempotent. Events remain admitted if a later cut refuses.
Both reads have one canonical path each. Their required query identities are opaque: slash,
literal percent sequences, interior spaces, plus signs, delimiters and Unicode retain their
admitted values. Encode query parameters once with the HTTP client's parameter encoder; never
split, normalize or decode them again. The unreleased portfolio/identity-segment routes have no aliases.
The positive exact revision is the only variable path identifier in these two operations.

For example, encode the original portfolio `portfolio/a`, producer `desk/feed` and record
`lot / A+1%2F` without changing their stored values:

```python
from urllib.parse import urlencode

print(urlencode({
    "portfolio_id": "portfolio/a",
    "source_system": "desk/feed",
    "source_record_id": "lot / A+1%2F",
}))
```

Append its output to the canonical lookup path, for example:
`/integration/financial-source-observations/flow-events/versions/1?portfolio_id=portfolio%2Fa&source_system=desk%2Ffeed&source_record_id=lot+%2F+A%2B1%252F`.
The literal `%2F` in the source record remains `%2F`; it is distinct from an original `/`.
Calls still require independently admitted tenant authority and an exact retained revision;
query parameters do not authenticate their caller or opt into a latest revision.

No distributed transaction or fabricated server ID is required. Per-fact verification receipts
are unsupported by this new family; no fact receipt grants monthly or institutional authority.

## Complete Membership And Traversal

At first publication, the manifest must name all distinct retained admitted event IDs for the
same tenant/portfolio/producer/currency/definition in the inclusive business window, including
cancelled and reversal events. Intentional subsets refuse. At most 1,000 combined event/dependency
observation pins are supported; overflow explicitly refuses instead of truncating. Historical
revisions may be pinned explicitly. Every target pin must resolve with exact hash/version,
tenant/portfolio/producer, currency and definition. Targets cannot have a later business date than
their reversing event. Dependency closure must be complete and reachable from window events,
with no orphan dependency, duplicate immutable pin, self-reference or source-event cycle, including
cycles through historical revisions.

A January reversal can target a December event, or a December reversal that targets November.
Those retained target revisions appear in `reversal_dependencies`, not in January `events` or
`pagination.total_count`. A historical revision of an in-window event is also a dependency when
the reversal explicitly targets it while the window membership selects a later correction.
Later target corrections never replace original target pins or silently restate retained cuts.

Event admission and cut publication acquire the same producer-scope transaction advisory lock.
The writer requires READ COMMITTED so membership reads after lock waits see committed arrivals.
Cut corrections use contiguous CAS and a unique successor. Exact retained-cut replay precedes
current membership checks: late arrivals never alter or invalidate a published historical cut;
they require a new corrected manifest. Completeness proves all retained admitted events at
publication, not that an external institution delivered every event.

One statement joins immutable cut pins, event revisions, admitted scope and completed event/cut
receipts. The entire bounded event/dependency set is validated before paging. Pages contain at
most 250 window events, ordered by event ID; the separate bounded dependency closure accompanies
each page. Window total count, dependency count/digest and the full combined ordered-set hash are
explicit. Signed cursors bind tenant, portfolio, cut, window, currency, page size, both evidence sets
and position. Consumers reconcile terminal cursor and both counts/digests across every page.
Matching dates or latest heads cannot replace pins, and dependency amounts cannot be counted as
current-window flows.

Complete explicitly empty coverage represents zero events. Absence refuses; partial/missing
coverage or UNKNOWN posting/reversal state makes `source_fields_available` false.
`authoritative_use_available` remains false, even for complete controlled synthetic input.

Manage maps `source_record_id`, `business_date`, actual `received_at`, currency, exact amount and
classification directly. `status` uses only explicit POSTED/CANCELLED posting state. Reversal
target mapping requires the explicit reversal declaration and full-cut validation. UNKNOWN,
missing receipts, incomplete pages and incompatible selections refuse usable assembly.

## Grants, Migration And Evidence

`LOTUS_PORTFOLIO_SOURCE_SUBMISSION_GRANTS_JSON` is a bounded public server configuration of exact
`tenant_id`, `portfolio_id`, `producer_id` and typed `family` grants. Blank defaults to no grants.
Malformed/unknown/duplicate fields, duplicate grants and wildcard scope refuse composition.
Canonical Compose forwards it only to ingestion. It is not authentication: independently trusted,
verified TenantContext must match tenant and producer service identity, and the exact
portfolio/family grant must exist. Body/header strings do not authenticate themselves. No private
signing key or institutional authority enters Manage.

Apply `c187b2c3d548` after `c186b2c3d547` before deploying these writers/readers. Three evidence
tables are added; old migration blobs and cash/funding data remain unchanged. Facts/cuts reject
update/delete, and nonempty truncate/downgrade refuses. No legacy backfill or financial booking
migration occurs. Existing cash/funding v1 hashes, DTO defaults and receipt timing remain intact.

Owning unit controls cover the explicit state matrix, exact amounts, pins, omissions, grants,
actual handler time, replay, cross-window/multi-hop closure and signed pagination. PostgreSQL
controls are authored for populated upgrade, same/prior-window and multi-hop retained reads,
original targets after late correction, rollback, correction races and immutability. The five
owning selectors are registered in critical DB coverage and the owning module in query-authority
validation; parameterized selectors collect seven cases. On 15 October 2026, signed source
`3cc2b7308b0f07d6f42ae5fdd64641bd28772e42` executed all seven in hosted PostgreSQL run
`38722916686`; they FAILED missing native endpoint evidence-policy classification. The passing
391 owning unit and 36 peer controls remain bounded source evidence, distinct from that failure.
Local native PostgreSQL, HTTP and restart remain unexecuted; corrected live acceptance is pending.
Migration inventory proves revision order only. No financial or production qualification is claimed.
