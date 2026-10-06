# FX Slice 6 - Realized P&L Baseline Semantics

## Scope
This slice establishes deterministic baseline realized-P&L behavior for FX rows before advanced cash-lot treatment is introduced.

## Delivered
1. FX baseline processing path now persists FX rows without routing them through the generic BUY/SELL cost engine.
2. `fx_realized_pnl_mode = NONE`:
 - realized capital P&L local/base = `0`
 - realized FX P&L local/base = `0`
 - realized total P&L local/base = `0`
3. `fx_realized_pnl_mode = UPSTREAM_PROVIDED`:
 - capital P&L defaults to explicit zero when omitted
 - total P&L defaults to capital + FX when omitted
4. Canonical FX validation is enforced before persistence on the FX bypass path.

## Key Design Decisions
1. FX capital P&L remains explicit zero.
2. Baseline implementation supports `NONE` and `UPSTREAM_PROVIDED` deterministically.
3. `CASH_LOT_COST_METHOD` remains a later extension and is not simulated implicitly in this slice.

## Persisted Return Qualification (#452 R2 candidate)

FX booking carries a detached, owner-qualified pre-write witness inside the existing financial
unit of work. When canonical loading has already acquired source locks and loaded original raw
facts, the repository hands those facts to booking without a second raw query. Otherwise it locks
only the target transaction row; it does not add portfolio or advisory serialization. The witness
does not relax `FirstPublicationSourceAuthority.matches` or grant economic correction authority.

`NONE` supports the existing raw-absent durable retention route without asserting raw authority.
`UPSTREAM_PROVIDED` requires exactly one original raw source with matching owner and material
identity. An unprocessed raw row requires the application's actual standard first-publication
claim and absent epoch; a processed row additionally qualifies its retained receipt under the
existing original-source policy. Original six Decimal/null values remain distinct from normalized
zero/defaulted totals, and the admitted source FX rate and origin must match.

The first persistence return may retain only an omitted `source_system` equal to the witnessed
pre-write value. All other persistence-shaped material and the submitted receipt remain exact.
Rebinding keeps the original six source values; a second return must equal the rebound row and
receipt. Refusal escapes through the existing financial UOW rollback before downstream effects.
Local unit proof is separate from native PostgreSQL write rollback, concurrent lock behavior,
protected promotion and exact-main validation. Those acceptance boundaries and broader #452
economic commands remain open; no schema, source-confirmation authority or policy floor changes.

## Fresh Source Admission

Canonical production FX with an explicit `UPSTREAM_PROVIDED` claim must supply both
`realized_fx_pnl_local` and `realized_fx_pnl_base`. Explicit zero and signed amounts are evidence;
totals do not substitute for missing FX. `FX_CONTRACT_OPEN` is non-realizing and exempt, as are
`NONE`, non-FX and generated cash types. Missing/unknown components cannot downgrade an explicit
claim. Existing business validation separately governs capital and conserving totals.

Activate this strict-forward contract only after deploying both `ingestion-service` and
`persistence-service`; a predecessor writer does not enforce the new admission policy. No schema
backfill or source-presence inference is part of this cutover.

The ingestion DTO rejects incomplete single requests and entire invalid mixed batches with
HTTP 422 / `FX_UPSTREAM_SOURCE_INCOMPLETE` before job creation/publication. Incomplete historical
HTTP resubmissions follow the same strict-forward rule. Raw persistence handles exact duplicates
first, then validates inside its existing UOW: refusal rolls back the claim and leaves no new
ledger/outbox/fence. A complete zero source after first refusal is first booking, not correction.

Raw upstream persistence identity `v3` binds all six original capital/FX/total local/base amounts,
distinguishing missing from supplied zero/signed values. Non-upstream v1/source-booked v2 hashes
remain unchanged. Locked immutable v3 ledger identity can qualify exact incomplete broker replay
after transient fence expiry without a ledger/outbox write. Ambiguous pre-v3 P&L-excluding identity
fails closed for upstream replay even when booked FX matches; old fingerprints/rows are not
rewritten or promoted. Caller receipts and mutable enriched columns are not reconstruction authority.

This admission slice changes no historical calculation, receipt, reader/QCP projection or
correction command. In particular it does not implement historical missing-versus-zero qualification
or the command-level revision model. The distinct real-PG matrix is
`tests/integration/services/persistence_service/test_fx_source_admission_postgresql.py`, selected by
the native FX contract and changed-code coverage lanes. Its captured broker is explicit: registered
HTTP/real consumer/PostgreSQL proof is not live Kafka or deployment certification. Exact-head native
execution, required protected checks and mainline validation remain necessary for acceptance.

## Evidence-Only Source Confirmation

The separate source-confirmation capability preserves the admission boundary above. It does not
resubmit an incomplete transaction, replace its economic identity, replay financial effects, or
rewrite original raw payloads and version-1 calculation receipts.

`POST /ingest/transactions/{transaction_id}/source-evidence` accepts a closed body containing
`expected_head_id`, `expected_head_sha256`, `reason`, and at least one explicitly supplied
`realized_pnl_local` / `realized_pnl_base` decimal-text field. These fields confirm original FX
source presence; they do not request new economic P&L. Missing source can be confirmed only as exact
zero, and every already-present signed companion remains unchanged. Null, nonfinite, inexact,
nonzero missing-source confirmation and incomplete confirmation of both missing bases refuse.

The dedicated verified capability is `ingestion.transactions.source_evidence.correct`. Signing
and consumption require explicitly enrolled, purpose-bound producer authority through
`LOTUS_SOURCE_CORRECTION_PRODUCER_ENROLLMENTS`; an absent enrollment or key denies. There is no
static-token fallback. The signed command binds tenant, target, operation, command identity,
expected head, reason, decimal values, supplied-field presence, correlation and trace.

HTTP 202 means `QUEUED`, not durable completion. The registered persistence consumer authenticates
before idempotency, borrows the existing CoreDB UOW and locks Operation SHARE, Portfolio KEY SHARE,
Transaction UPDATE, retained raw KEY SHARE and revision head KEY SHARE in that order. It verifies
the original retained source, complete original receipt and expected-head CAS, then appends one
immutable `transaction_source_revisions` fact and one `TransactionSourceEvidenceChanged` notice in
the same transaction. A committed retry still requires valid crypto and independently requalified
complete fact/source/receipt authority; expiry alone does not force another effect.

Follow the returned status URL through the existing event-replay owner at
`GET /ingestion/jobs/{job_id}/source-correction`. Only independently reloaded, tenant-owned,
completely qualified revision authority is `SUCCEEDED`. Accepted intent is `QUEUED`; unavailable
or inconsistent authority never exposes a successful revision identity. The notice has no
registered downstream consumer and is not analytics qualification.

Migration `c177b2c3d538` is additive and starts with an empty revision table: no legacy transaction,
raw event, receipt or job is promoted by backfill. Database UPDATE/DELETE refusal preserves revision
history. Empty-table downgrade is supported; populated-history downgrade refuses rather than
discarding durable evidence. Schema extraction preserves named-column/default/constraint/index
metadata and keeps monetary declarations discoverable by the native numeric guard.

The owning proof is
`tests/integration/services/persistence_service/test_transaction_source_correction_postgresql.py`.
Explicit broker substitutes, unit registration and collection alone do not establish live Kafka,
QCP/ledger consumer qualification, source-cut invalidation, exact-main release, production identity
enrollment, or broader economic correction/reversal/rebook. Those remain separate acceptance
requirements; issues #452, #1176 and #531 are not closed by this foundation.

## Producer Input And Consumer Source Cuts

The version-2 baseline producer binds all six original capital/FX/total local/base presence/value
pairs before normalization through `fx-original-pnl-presence@2`. Missing original amounts and
explicit zero produce distinct input hashes even when normalized financial outputs are equal.
Baseline cost/P&L calculations remain unchanged. Original version-1 receipts stay immutable and
require independent retained raw evidence; stored zero never reconstructs source presence.
Unsupported policy, changed original input, output mismatch, ambiguous roots or foreign ownership
fail closed.

QCP `PerformanceComponentEconomics:v1` and operational ledger reads share a closed
`TransactionSourceEvidence` contract. It identifies admitted tenant/portfolio/transaction, retained
raw root, qualification, selected immutable revision/hash and confirmation time. It exposes neither
raw payloads nor signed authorization material. Notification metadata does not establish an external
Performance consumer or Kafka subscriber.

The existing `GET /portfolios/{portfolio_id}/transactions/{transaction_id}` route selects evidence:

| Selection | Query | Authority |
| --- | --- | --- |
| Current | `source_evidence_selection=current` | Fully qualified linked current revision, or original authority when no revision exists. |
| Original | `source_evidence_selection=original` | Immutable original raw/output/receipt; no correction revision, intent or operation enters the cut. |
| Explicit revision | `source_evidence_selection=revision&source_revision_id=<owned-revision-id>` | Exact tenant/portfolio/transaction-owned revision; unknown or foreign identity is indistinguishable from absence. |

No second history API or alias is introduced. A revision identifier is required only for explicit
revision selection. Original reads remain equal across confirmation except descriptive generation
time; current/explicit evidence may qualify only a genuinely absent source as zero. Signed
companions, capital/total identities and original financial/raw/receipt values remain unchanged.
Unqualified FX and dependent totals stay null, not inferred from normalized storage.

QCP establishes `REPEATABLE READ, READ ONLY` before portfolio/currency/scope reads and captures
the entire matching-window material cut once. Ledger retains first-read snapshot discipline and
binds the same selected authority into its input cut. `source_cut_sha256` is material authority:
confirmation outside the returned page can change it. QCP continuation binds the same cut and
request scope; stale or legacy unbound tokens refuse. A failed/late snapshot cannot yield READY.
Latest evidence time is descriptive, not cut authority. Confirmation time records acquired
knowledge; transaction date and requested business as-of date still govern financial visibility.

The existing owning source-correction PostgreSQL file exercises genuine retained version-1 and
current version-2 producers, separate reloads and actual QCP/ledger services with a controlled
signed broker substitute. Six consumer cases preserve zero/positive/negative companions and
immutable originals, and refuse stale outside-page cuts, foreign/unknown revisions, late snapshots
and tampered source. Native execution is required; collection/prior-foundation proof does not
qualify a changed cut. Live Kafka, deployed enrollment, downstream analytics, exact-main release,
general economic correction and whole-issue closure remain separate acceptance requirements.

## Shared-Doc Conformance Note
Validated against:
1. `05-common-validation-and-failure-semantics.md`
2. `06-common-calculation-conventions.md`
3. `09-idempotency-replay-and-reprocessing.md`

## Residuals
1. No advanced cash-lot realized FX engine yet.
2. No MTM/unrealized contract valuation yet.

## Exit Evidence
1. `tests/unit/services/portfolio_transaction_processing_service/application/cost_basis_processing/test_execution.py`
2. `tests/unit/libs/portfolio_common/test_fx_validation.py`

