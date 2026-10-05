# Transaction Processing

`portfolio_transaction_processing_service` is the single runtime owner for atomic cost, cashflow,
and position mutation after a transaction is persisted. It keeps those financial policies
modular while sharing one transaction boundary, idempotency decision, and compatibility outbox.
Current scope is the implemented combined transaction worker and its service-owned ordinary
transaction domain; valuation, timeseries, and downstream analytics remain separate capabilities.

## Reader Map

| Reader need | Start here | Evidence posture |
| --- | --- | --- |
| Understand atomic processing ownership and rollback | [Processing Flow](#processing-flow) | One application use case and one SQLAlchemy unit of work own the combined mutation. |
| Verify settlement and FX fee economics | [Ordinary Settlement Cash](#ordinary-settlement-cash) | Stable reason codes and warning-strict domain, application, and lifecycle tests protect current policy. |
| Understand corrected redemption field presence | [Redemption Correction Semantics](#redemption-correction-semantics) | Omission, exact zero, and generated-child link retirement have distinct durable meanings. |
| Extend transaction behavior without crossing layers | [Extension Rule](#extension-rule) | Domain policy, application ports, and named infrastructure adapters remain separate. |
| Assess compatibility and current limitations | [Compatibility](#compatibility) | Existing event and persistence contracts remain authoritative unless a versioned change says otherwise. |
| Locate executable proof | [Evidence](#evidence) | Repository-native manifests and architecture guards are the closure evidence; wiki prose alone is not proof. |

## Processing Flow

Before processing, fresh applicable FX `UPSTREAM_PROVIDED` sources require local/base FX P&L;
zero and signed amounts are valid. HTTP rejects incomplete sources before publication. Raw
persistence handles exact duplicates first, then admission in the existing UOW; fresh refusal
leaves no ledger/outbox/fence. Exact locked v3 durable replay may qualify after fence expiry;
ambiguous P&L-excluding pre-v3 identity cannot promote stored zero. No reader, calculation or
historical row is rewritten. A complete source after first refusal is first booking, not correction.
See the [FX admission policy](https://github.com/sgajbi/lotus-core/blob/main/docs/rfc-transaction-specs/transactions/FX/FX-SLICE-6-PNL-SEMANTICS.md#fresh-source-admission)
and its candidate-specific PG matrix. Captured publication is not live Kafka certification.

1. The live or replay-request consumer receives the existing governed transaction event.
2. Infrastructure maps the event DTO to immutable `BookedTransaction` domain data.
3. The application use case coordinates cost, cashflow, and position modules through ports.
4. Domain policies calculate state changes without importing Pydantic, SQLAlchemy, Kafka, metrics,
   or repository implementations.
5. Infrastructure adapters persist all changes and compatibility outbox events in one database
   unit of work.
6. A failure rolls back the combined state transition; replay uses the same application path.

The combined unit of work owns session lifecycle and adapter composition only. Transaction claim
persistence, the stable processing service identity, and physical/semantic outcome translation live
under `app/infrastructure/idempotency`; application orchestration consumes them only through
`TransactionIdempotencyPort`. Do not add concrete claim repository behavior back to the unit of
work or expose the adapter through the broad infrastructure package root.

The concrete atomic boundary is
`app/infrastructure/transaction_processing/unit_of_work.py`. It composes cost, cashflow, position,
readiness, idempotency, and outbox adapters over one SQLAlchemy session and one commit. The class is
not exported from the broad infrastructure root; runtime builders obtain it through the aggregate
transaction-processing package.

Concrete use-case builders live at `app/runtime/dependency_composition.py`. The live/replay consumer
composition and the AVCO reconciliation operator command import this explicit composition root;
infrastructure packages expose adapters, not application assembly functions.

The `app/infrastructure` root is namespace-only. Runtime code and tests import adapters through
their named capability packages so cashflow, cost basis, position, idempotency, mapping, processing,
readiness, and replay ownership remains visible in every dependency.

The event anti-corruption boundary is `app/infrastructure/transaction_mapping`. Its
`booked_transaction` mapper preserves all governed envelope and domain fields in both directions;
its `foreign_exchange_instrument` mapper translates synthetic FX contract domain values to the
governed instrument event. Domain and application modules remain independent of Pydantic event
models, and new transaction event translations belong in this package rather than flat
infrastructure files.

Booked-transaction replay remains a separate application use case because operator replay has
different backlog, recovery, and delivery controls. Its infrastructure adapter lives under
`app/infrastructure/transaction_replay`, opens a short-lived SQLAlchemy session, delegates to the
canonical publisher, maps dependency failures, and enforces that one transaction ID publishes zero
or one record. Delivery code owns retry and DLQ handling; replay infrastructure is not exported from
the broad infrastructure package root.

Aggregate live and replay stage telemetry is an infrastructure adapter under
`app/infrastructure/transaction_processing`. It implements the application observer port and keeps
Prometheus counters, histograms, clocks, and telemetry-failure containment outside application and
domain code. The adapter is not a broad infrastructure-root export, and metric names, bounded stage
and outcome labels, and failure behavior remain operational contracts.

## Ordinary Transaction Domain

### Cashflow and history epoch coherence

Before cashflow idempotency and readiness, the combined application binds every unversioned
financial-effect transaction to the authoritative locked epoch of its materialized portfolio and
security. Explicit epoch zero, current/future epochs and rebuilt transaction epochs are preserved
for their existing fences. Missing lock evidence (`financial_effect_epoch_unavailable`) or
unversioned ignored/coalesced position work without materialization
(`position_materialization_unavailable`) refuses the financial effects and rolls back the unit of
work. Explicit stale input retains its existing nonretryable cashflow epoch rejection. Raw semantic
duplicates are suppressed before position processing. For ordinary first-CLAIMED unversioned
REPAIR, existing cost/security and applicable group locks precede Portfolio and Transaction locks.
The canonical source must match DB ownership and the complete original source fingerprint before
costs; that admission permits native position rebuilding without guessing an epoch. Existing
correction and repair-delivery paths retain their own authority. The registered
`/reprocess/transactions` route replays canonical DB transaction
fields through `transactions.reprocessing.requested`; verify those source fields and the actual
selected cut before promising recovery. Do not add a repair header or rewrite a source epoch.
Repeated delivery cannot
supply missing materialization authority. There is no epoch-zero or latest-row
fallback. Cashflow ledger dates, original trade timestamps, signed economics and source identity
are unchanged.

Concurrent ordinary backdated work can reuse a completed current-epoch materialization only
when the same unit of work retains an exact tenant/key/epoch/quantity position receipt and
qualifies the pre-existing cashflow semantic receipt plus complete historical output and lineage.
Portfolio, state, replay and history locks protect that position receipt until commit or rollback.
History without the required financial receipt still refuses completion/replay. A separately
qualified first publication is limited to ordinary fresh CLAIMED, unversioned input. Its current
unit of work qualifies the exact canonical tenant/key/full original fingerprint under source and
cost locks before cost writes. Only the matching successful current cost member and typed locked
position epoch/quantity receipt admit native CURRENT_BOOKING cashflow, readiness and outbox
staging in that same atomic unit of work. Unknown epoch, absent quantity, foreign source and
generated-member inheritance refuse; actual zero quantity remains distinct from missing evidence.
Optional proof absence never relaxes the completion guard. Repair, correction, duplicate and stale
epoch routes retain their own authority, including existing scoped no-cash receipts.

For example, processing DEPOSIT1000 can materialize a pending same-day DEPOSIT500 position1500
or SELL100 position900. The pending first financial delivery uses its own qualified source and
locked position receipt to create +500 external deposit cash or +100 internal sale proceeds at
the current booking context exactly once. SELL reduces position quantity by100 while cash-ledger
sale proceeds are positive; cost reduction and analytics investment measures have distinct signs.
Positions are not restated and duplicate delivery adds no cashflow/readiness/outbox effects.
This bounded admission is not certification of broader HTTP/Kafka/live or concurrent processing.

Declared FX contract open/close
routes use a distinct completed no-cash stage receipt and require no transaction/epoch cashflow
row; missing evidence is not success and a zero cashflow is not manufactured.

Derived financial reconstruction reuses the existing fee qualifier, booking metadata policy and
actual portfolio cost method for full and bounded replay. Positive, explicit-zero and absent
named fees retain distinct qualified source presence. Bounded hypotheses require an exact
original hash or independently committed scoped material receipt; a stale aggregate, absent
cost rows or calculated net cost supplies no authority. This derived context does not relax
default original-source validation or rewrite its immutable hash. Tenant ownership is checked
through scoped admission and SQL joins, because the financial fingerprint does not bind tenant.
Legacy history without an original hash remains readable as historical representation, but the
exact coalesced financial lookup refuses it as unqualified source authority.

For a gross booking amount of 50, qualified source fee presence produces these cash outflows:

| Qualified original booking inputs | Persisted derived aggregate | Cash outflow |
| --- | --- | --- |
| Named fees 1.25 + 0.75 | Stale 99 | 52 |
| Explicit-zero named fees | Stale 99 | 50 |
| Absent named fees; original aggregate 99 | 99 | 149 |

The original aggregate in the last row is a booking input. The stale derived aggregate in the
first two rows cannot override qualified named presence. Source qualification and tenant admission
remain separate checks.

The date-bounded reader preserves its prior anchor and ordered window. These source and native
database controls do not certify the registered recovery endpoint, live joined safety or closure.

The service-owned replay reader qualifies named fees before the shared planner publishes the
batch. Existing cost/raw rows provide fixed amounts; original raw payloads must match the stored
full source hash. A prior-claimed transaction without retained raw evidence may recover fee
presence from an independently committed, exact tenant/service/portfolio/ordinary semantic-key
processing receipt using the unchanged service material identity. Each of the five named fields
retains None or explicit zero; positive amounts cannot be invented. The existing aggregate-only
brokerage ledger allocation remains an allocation, not an original named brokerage fee. At most32
component hypotheses, or64 with a uniquely receipt-qualified aggregate None/zero hypothesis and
no contradictory positive amount, may produce one projection. No match or conflicting evidence
requires disposition. No new store, retention guarantee, latest receipt or source-hash policy
exists. First-CLAIMED validation never uses this fallback or its newly inserted invocation claim.

Receipt proof is the existing material-processing contract, not full original ingestion
representation. Generated booking defaults retain their domain normalization; changed economics
and custom metadata remain material. Exact None-input epoch/version is mandatory: explicit0 or
another epoch cannot certify it. Source-booked v2 FX must match; disagreement cannot downgrade
to v1, and a v1-only receipt cannot prove historical source FX value or presence. Physical-only,
correction, unrelated tenant/service/portfolio and absent receipts do not qualify this ordinary
fallback.
If a supported historical case lacks sufficient facts, preserve it and return the authority gap;
do not relabel a compatibility regression as an acceptable refusal.

Historical derived financial projection has a separate correction rule, enabled only together
with retained-receipt qualification. A committed exact correction key and fingerprint must bind
the current tenant, service, portfolio, transaction, source epoch, version and complete material
cut. The pre-existing ordinary epoch/version fence must remain present and consistent. One
additional locked batch computes exact correction keys after fee rows are loaded; its query count
does not grow with the number of transactions. Only a unique qualified fee-presence projection
may supersede the old ordinary material receipt for this corrected cut. Missing, conflicting,
ambiguous or in-memory correction evidence cannot authorize it. Original raw/full-hash authority
and ordinary receipts are never rewritten, and first-CLAIMED/default source validation is unchanged.

Within the correcting unit of work, position rebuilding instead receives the immutable admitted
root identity and complete cost-result member group. It verifies the active persisted row and
locked replay epoch before history deletion; this group is not historical authority for a later
ordinary transaction. Generated cash legs forward the actual canonical upsert return, retaining
the source epoch explicitly. Exact nonpersistent lot-restatement context must match the existing
finite Decimal quantity, direction and ratio policy rather than relaxing financial comparison.
These source contracts do not certify supported correction ingestion or live joined safety.

For legacy mismatch diagnosis, capture the analytics reader's actual snapshot epoch and rank the
cashflows it selects by transaction at or below that cut. Check same portfolio/transaction/trimmed
security/epoch history for those selected rows. An older orphan superseded by a valid selected
epoch is not a current failure. Retain the database backup and exact selected-key evidence before
any repair. A missing selected history key remains insufficient evidence; do not use a mutable
Transaction date, another epoch's history or zero flow to make the request succeed.

After deploying the qualified producer change, an authorized operator can use the existing
canonical booked-transaction replay/repair route for the exact affected original transaction ID,
with its governed repair-delivery identity and audit evidence. The repair consumer uses the same
combined transaction unit of work; ordinary duplicate delivery alone may be suppressed and does
not repair derived state. Preserve original booked dates, gross amounts, currencies and pairing,
then verify exact same-epoch history/cashflow keys, reader selection, readiness and independent
financial figures. If source authority or repair admission is unavailable, stop for disposition.
No direct SQL epoch/date rewrite, forced latest join or destructive reseed is a repair policy.
A clean seed or a focused PostgreSQL pass does not certify all deployed historical cursors or
replace a source-pinned full live validation.

The owning PostgreSQL controls are in
`tests/integration/services/portfolio_transaction_processing_service/test_int_position_history_repository.py`:
funded paired cash suffix replay, retained epochs, rollback after staged writes and late unversioned
interest delivery with duplicate/repair controls, full first-claim deferred rollback, source
refusals before costs, native stale CAS/rearm and concurrent root/receipt controls. Retained-no-raw
controls use QCP's actual snapshot selection and cashflow ranking with a labeled serving-row
fixture: the old orphan refuses, and the selected repair has same-epoch trade-date history and
the original signed amount. This does not certify valuation publication, the registered HTTP
delivery or full joined runtime. Application tests cover missing lock evidence, no materialization,
explicit fences, generated multi-effect rebuilding and distinct portfolio/security scopes.

The service-owned `app/domain/transaction` package owns ordinary BUY, SELL, DIVIDEND, and INTEREST:

- booking metadata and stable policy identifiers,
- validation findings and reason-code values,
- cash-entry mode policy,
- generated settlement cash-leg economics and linkage,
- upstream-provided product/cash-leg pairing.

These policies consume `BookedTransaction`. Existing event envelopes are mapped only in
infrastructure, where schema version, event type, correlation, trace, and other governed metadata
must be preserved.

Most validation functions remain contract-conformance evidence. The one active settlement boundary
is non-positive proceeds after resolved fees for SELL, DIVIDEND, and INTEREST income. The application
classifies physical and semantic idempotency inside the combined unit of work first, then rejects a
newly claimed or repair delivery before cost, position, cashflow, or commit. Harmless historical
duplicates remain acknowledgements. Other strict-metadata validators remain conformance-only until
an intentional behavior decision, compatibility review, tests, and contract documentation activate
them.

## Ordinary Settlement Cash

One transaction-domain policy resolves fee precedence, signed cash amount, and ledger direction:

| Transaction | Signed settlement cash |
| --- | --- |
| BUY | `-(gross amount + resolved fee)` |
| SELL | `gross proceeds - resolved fee` |
| DIVIDEND | `gross dividend - source-recorded withholding - resolved fee` |
| INTEREST income | `pre-fee net interest - resolved fee` |
| INTEREST expense | `-(pre-fee net interest + resolved fee)` |

Component fee fields take precedence over aggregate `trade_fee` when any component is present.
SELL, DIVIDEND, and INTEREST income must remain strictly positive before the inflow sign is applied.
Zero or negative proceeds are non-retryable hard rejections with stable family codes; absolute-value
normalization must never turn invalid proceeds into an apparent inflow. Generated settlement legs
and persisted product cashflows consume the same policy result.

For current DIVIDEND booking, the existing nullable `withholding_tax_amount` is preserved as
separate ledger/query evidence and reduces available settlement proceeds before the fee. Negative
withholding, withholding above gross, or non-positive resulting cash fails closed with stable
`DIVIDEND_014`, `DIVIDEND_015`, or `DIVIDEND_013` reason codes. Null and zero withholding preserve
the prior gross-minus-fee result. Every output produced by current cost processing retains
current-booking economics when it participates in an inline rebuild, including transformed or
split identities. Previously accepted suffix rows receive the explicit historical-rebuild context,
but source-recorded positive DIVIDEND withholding remains in product-cashflow economics so rebuilt
product and generated cash legs stay reconciled. Null/zero withholding and rows that predate the
current settlement fences retain legacy arithmetic.
Withholding-rate derivation, other receipt deductions, a supplied-net identity, return-of-capital,
basis reduction, and advanced timing remain tracked under #448.

## Generated Transaction Identity Ownership

Generated settlement cash and redemption accrued-interest transactions use stable identifiers,
but the identifier suffix is not proof of ownership. Core recognizes a generated child only when
its complete portfolio, originating transaction, transaction family, component, and link metadata
agree. Source bookings that merely resemble a generated identifier remain source-owned.

Both transaction persistence paths enforce ownership inside the PostgreSQL conflict statement.
An existing row may be replayed or corrected only by the same portfolio, generated family, and
origin. A source/generated, cross-portfolio, wrong-origin, or cross-family collision fails closed
with `generated_transaction_identity_collision` before downstream effect staging. This is an
intentional correctness tightening; ordinary source replay, event shapes, Kafka topology, database
schema, and generated identifier formats are unchanged.

## Redemption Correction Semantics

Ordinary transaction upserts remain sparse for compatibility. A semantic redemption correction is
authoritative for its complete optional economics set: redemption price type, old/new factor,
principal proceeds, accrued-interest proceeds, embedded fee, and embedded tax. When a corrected
value is omitted, Core persists SQL `NULL`; when it is exactly zero, Core persists zero. This keeps
replay, query, cashflow, P&L, and calculation lineage aligned to the corrected command instead of
retaining superseded source authority.

Generated accrued-interest income can remain positive when corrected settlement is exactly zero.
On that correction-only path, Core loads the prior deterministic interest child and explicitly
clears any retired cash-leg and component links. Ordinary bookings incur no additional child read,
and generated transaction identity remains stable.

FX fees and taxes use a separate-linked-posting policy. A non-zero aggregate or component fee on an
FX spot, forward, swap, or generated cash-settlement leg fails before booking, cost mutation, or
cashflow sign normalization with `FX_025_NON_ZERO_EMBEDDED_FEE`; non-zero inline
`withholding_tax_amount` fails at the same boundaries with `FX_026_NON_ZERO_EMBEDDED_TAX`. Absent
and zero inline charges retain
existing economics. Book supported charges as distinct `FEE`/`TAX` transactions carrying the same
`economic_event_id` and `linked_transaction_group_id`; do not infer fee currency or charged-leg
ownership from either FX cash leg.

## INTEREST Settlement Economics

For INTEREST, `net_interest_amount` is after withholding tax and other interest deductions but
before separately reported transaction fees. One domain policy now owns reconciliation, generated
cash-leg, and persisted cashflow arithmetic:

| Direction | Settlement cash magnitude |
| --- | --- |
| `INCOME` | `net_interest_amount - transaction_fee` |
| `EXPENSE` | `net_interest_amount + transaction_fee` |

Cashflow sign records the income inflow or expense outflow. An explicit conforming net amount and
the equivalent derived net amount must produce the same settlement cash. This corrected the prior
fee-bearing source-shape difference; it did not rename fields, reason codes, events, or database
columns. Downstream consumers needing settled cash should use the linked cashflow amount rather than
treating `net_interest_amount` as fee-inclusive cash.

For a current booking, an explicit pre-fee net that does not reconcile to gross interest less
withholding and other deductions is rejected with
`INTEREST_015_NET_RECONCILIATION_MISMATCH` after idempotency classification and before financial
writes. Historical rows already accepted before this active boundary retain their pre-policy
economics only when Core supplies them through the explicit position-history rebuild context.

Gross interest less withholding and other deductions must be non-negative before fees. The single
and batch ingestion DTOs, canonical transaction event, current-booking service, and replayed direct
processing path reject both omitted and explicit negative forms with
`INTEREST_018_NEGATIVE_PRE_FEE_NET`; the service rejection is non-retryable and occurs before
financial writes. A positive expense fee cannot mask a negative pre-fee amount. Zero pre-fee
expense plus a fee remains a supported fee-only outflow.

## Shared-Library Boundary

Corporate-action execution releases use owner, token, monotonic fence, and database-clock expiry
as one durable authority. Claim, payload load, member progress, terminal failure, next-member load,
and renewal compare expiry against PostgreSQL statement-current `clock_timestamp()`. Transaction-
start `now()` is not lease authority because row-lock waits or an aged transaction must not let an
expired worker advance financial state. The public transaction/event contracts and calculation
economics are unchanged by this persistence fence.

`portfolio_common.transaction_domain` is retired. Ordinary settlement, corporate-action, FX, and
effective-processing policies are owned by the unified transaction-processing domain. Shared
libraries retain only owner-neutral event contracts, controlled vocabularies, normalization, and
infrastructure support. Do not recreate transaction policy facades in the shared package or the
retired calculator source roots. FX canonical values are immutable and framework-independent;
transport events are mapped at delivery and infrastructure boundaries.

## Extension Rule

For a new transaction type:

1. model the economic facts in domain language without framework objects,
2. place reusable ordinary booking or settlement policy under `app/domain/transaction`,
3. keep cost, cashflow, and position calculations in their distinct domain modules,
4. map transport and persistence representations at infrastructure boundaries,
5. add lifecycle, replay, idempotency, dual-leg, and rollback tests before runtime activation.

## Compatibility

The consolidation preserves public field names, event versions, topic names, database schema,
generated product/cash event ordering, and downstream response shapes. Current-booking DIVIDEND
cash intentionally changes only when the existing withholding field is non-zero; null/zero
withholding preserves prior behavior. INTEREST fee-bearing settlement arithmetic and rejection of
fee-equal or fee-dominated SELL, DIVIDEND, and INTEREST income remain documented intentional
behavior corrections.

## Evidence

- [Architecture](Architecture)
- [Cost Processing](Cost-Calculator)
- [Cashflow Calculator](Cashflow-Calculator)

### Deterministic transaction-ledger reconstruction

`TransactionLedgerWindow:v1` keeps its public response schema but binds its reconstruction scope
identity to the complete filtered material input set: transaction rows, owned transaction costs,
the latest cashflow selected per transaction, and applicable reporting-currency FX rows. The
database reduces each family to an ordered fixed-width digest; pagination and unrelated or
superseded rows do not alter the identity. A selected economics-input correction does alter it,
preventing stale page/cache reuse without transferring the complete ledger solely to construct
evidence. Evidence, page rows, instrument checks, and reporting-FX conversion execute within one
repeatable, read-only PostgreSQL snapshot, so a concurrent correction cannot split one response
across old and new committed states. Evidence and conversion also share the deterministic
`rate_date DESC, id DESC` selector for normalized legacy FX-pair variants. Date and timestamp
inputs are normalized to fixed UTC/ISO text before hashing, so connection `TimeZone` or `DateStyle`
cannot alter an otherwise identical reconstruction identity.
- [Position Processing](Position-Calculator)
- [Validation and CI](Validation-and-CI)
