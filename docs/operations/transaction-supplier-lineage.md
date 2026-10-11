# Transaction supplier lineage

Transaction ingress accepts optional `source_record_id`, `source_batch_id` and timezone-aware
`observed_at`. Supplying any of them requires a nonblank `source_system`. These are supplier facts;
Lotus never derives observation time from receipt, trade or settlement time. Unknown `source_*` or
`observed_*` fields fail validation rather than disappearing from a validated request.

`source_record_id` means the supplier's record identity. It does not alias
`source_transaction_reference`, whose corporate-action child-reference semantics and material
identity classification remain unchanged. Supplier lineage does not change the financial payload
fingerprint, semantic key, numerical calculations or correction admission.

## Retention and replay

The existing ingestion event, native persistence consumer and transaction row carry these fields.
Raw persistence inserts once. An economically identical replay retains the original row and original
lineage, even if transport metadata differs. Changed economics remains a semantic conflict.
The processing command carries lineage unchanged; processor updates cannot replace accepted lineage.
The database also rejects changes to accepted record/batch/observation fields, including attempts to
fill legacy unknown fields. The accepted source system cannot change in place either, consistent
with its existing material identity classification.

Restricted transaction and portfolio-bundle jobs remain fingerprint-only and replay-ineligible.
An existing job retains a bounded `transaction_batch_lineage` projection containing only one proven
system/batch scope or an unavailable reason. It retains neither the restricted request body nor its
economics or per-record source identifiers. This projection has the existing job's operational
evidence retention authority; technical request-payload expiry does not confer replay authority.
An ingestion acknowledgement or job batch identity proves submission lineage, not successful
booking, downstream effects or supplier authority. Consult the existing failures/DLQ evidence.

## Batch evidence and ledger reads

`IngestionEvidenceBundle` and `TransactionLedgerWindow` publish `source_batch_fingerprint` only when
their complete transaction scope proves one `(source_system, source_batch_id)`. The fingerprint uses
the existing source-batch identity helper with tenant and transaction payload kind. It identifies
that declared supplier batch, independently of economic contents, returned page membership and
Lotus attempt identifiers. It is not a response content hash or certification of batch completeness.

`source_lineage.batch_lineage_scope` is `transactions`. `batch_lineage_status` is `PROVEN` or
`UNAVAILABLE`, with `batch_lineage_reason` of `PROVEN`, `MIXED_BATCHES`, `LEGACY_UNKNOWN` or
`EMPTY_WINDOW`. Missing lineage never becomes invented historical provenance. A portfolio bundle's
transaction evidence does not assert one batch for its other payload families. A reprocessing
request containing only transaction identifiers supplies no new upstream batch proof.

The ledger computes batch evidence over the full filtered window under its existing read snapshot,
including rows outside the returned page. Use the existing
`GET /portfolios/{portfolio_id}/transactions?source_system=OMS_PRIMARY&source_batch_id=OMS-20230115-PM`
filters for reconciliation; tenant and portfolio admission still apply. Each returned row retains
its individual record, batch and observation values. Current/original/selected source-revision reads
retain their existing semantics: this batch metadata describes the accepted booking's ingress,
not a replacement authority assertion for a later confirmed source revision.

## Compatibility and migration

Transaction producers supplying new lineage declare schema `1.1.0`. Governed transaction consumers accept `1.0.0` and
`1.1.0`; other event families retain their existing version allowlist. Existing model-only legacy
envelopes remain consumable. The broader mandatory-version residual on #467 remains separate.
Deploy compatible consumers before producers supplying lineage. When lineage is absent, omit the
three extension fields rather than serializing new null defaults; legacy request HMACs and raw wire
shape remain unchanged. Explicit null values follow the same legacy representation.
Supplier-lineage policy errors return HTTP 400 with stable `detail.code`; unrelated request
validation retains its existing HTTP behavior.

Migration `c186b2c3d547`, after merged valuation-tenant revision `c185b2c3d546`, adds nullable
transaction columns, the `(source_system, source_batch_id)` index, the nullable job projection
and the immutable-lineage trigger. Existing rows remain null;
there is no synthetic backfill. Production uses forward fixes. A nonproduction downgrade refuses
when retained transaction lineage or a job projection would be destroyed.

The forward revision composes the existing classification, model-window and valuation-tenant
history; it does not rewrite those merged revisions or branch the migration head. The shared
`TransactionSourceColumns` mixin owns provenance columns without returning extracted valuation
constraints to the ORM monolith. Tenant admission, missing-versus-zero source posture, FX and
PnL policy, source-confirmation semantics and monetary-float enforcement remain unchanged.

## Validation and authority limits

Run from the `lotus-core` checkout. With `LOTUS_WORKSPACE_ROOT` set to the directory holding
the Lotus checkouts, resolve Platform explicitly when Core is in a separate worktree.

PowerShell:

```powershell
$env:LOTUS_PLATFORM_ROOT = Join-Path $env:LOTUS_WORKSPACE_ROOT 'lotus-platform'
make ingestion-contract-gate openapi-gate domain-product-validate
make test-query-authority-db-contract
make test-unit-db
```

Bash:

```bash
export LOTUS_PLATFORM_ROOT="$LOTUS_WORKSPACE_ROOT/lotus-platform"
make ingestion-contract-gate openapi-gate domain-product-validate
make test-query-authority-db-contract
make test-unit-db
```

The registered HTTP/native PostgreSQL tests explicitly substitute the broker; they do not certify
Kafka transport, a complete financial runtime or institutional sign-off. Existing correction and
source-confirmation contracts require their own authority and retain original booking lineage.
Broader #452 booking/correction acceptance remains separately governed.

Supplier traceability helps banking reconciliation and Composite financial-source qualification.
It does not by itself establish monetary authority, gross-cost validity, a whole-source cut or
institutional certification.
