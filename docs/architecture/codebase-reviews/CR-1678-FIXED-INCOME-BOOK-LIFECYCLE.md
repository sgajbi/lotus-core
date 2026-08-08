# CR-1678: Fixed-Income Book Lifecycle

## Scope

This review governs the bounded fixed-income batch for GitHub issues #451, #478, #481, and #477,
with a partial contribution to #788. It covers explicit quote authority, amortized-cost evolution,
lot-disposal lineage, and maturity/call/partial-redemption economics in their required dependency
order.

## Findings

The authoritative valuation runtime had complete policy vocabulary but no source-owned face or
current-principal fact. Review proved that persisted position `quantity` can represent instrument
units rather than nominal face, so relabelling it as principal would understate supported legacy
bond examples by 1,000 times. Independent reconciliation therefore cannot safely reproduce a
percent-of-face receipt from the current projection.

The amortization RFC also contradicted its own roll-forward: its straight-line numerator made a
premium increase and a discount decrease. It left effective yield ambiguous between annual and
per-period interpretations, allowed broad fixed-income classification to imply eligibility, and did
not require authoritative clean acquisition cost even though the current BUY default can include
accrued interest in book cost.

Runtime review found three hard dependencies before redemption can be enabled:

- amortized cost must be effective-dated per source lot and must not overwrite tax/original lot cost;
- every disposal needs an immutable per-source-lot allocation receipt under #481;
- linked redemption product/principal-cash/optional-interest legs need a persisted canonical group
  sequence and correction identity; Kafka arrival order alone is not processing order.

Issue #911 later proved that persistence of the group identity was necessary but insufficient:
portfolio/security serialization does not coordinate a redemption and an independent `INTEREST`
leg booked on different securities. Both transactions could read an incomplete group and commit
the same interest economics.

## Linked Redemption Group Serialization

Transaction processing now acquires advisory transaction locks in one explicit order:

1. normalized portfolio/security cost-basis stream;
2. normalized portfolio/linked-transaction-group, only for a redemption with positive accrued
   interest proceeds or an `INTEREST` leg carrying a linked group;
3. linked-group history read and all subsequent mutation within the same unit of work.

No path acquires a second security lock or the two locks in reverse order. Unlinked transactions,
unrelated groups, and different securities therefore retain their prior concurrency. The losing
authority receives `REDEMPTION_017_DUPLICATE_LINKED_INTEREST`; its unit of work rolls back without
calculation lineage or derived economic evidence.

The ingestion command contract now normalizes linkage identifiers and fails closed when either
identifier is absent for a governed redemption, `UPSTREAM_PROVIDED` product leg, or explicit
upstream cash leg. Product/cash pairing requires the same non-empty identifiers on both records.
The conditional requirements are published in the generated schema without changing the wire
field names. `linked_redemption_group_lock_wait_seconds` and the app-local dashboard expose bounded
`acquired`/`failed` wait outcomes without portfolio or group identifiers as metric labels.

## Corrections To Date

The scoped valuation path now keeps position quantity and face principal semantically distinct.
Authoritative unit-price behavior remains supported, while face, factor-adjusted, and independently
supplied current-principal policies fail closed until a source-owned principal fact or governed
units-to-face conversion is available. A framework-free local valuation-economics seam owns scaling
once, and independent reconciliation uses it only for supported unit-price receipts. Its
deterministic lineage binds the actual source value, signed quantity, principal inputs, and complete
valuation-policy identity, so equal outputs from different economic inputs cannot collide.

RFC-AMORTIZATION-01 version 1.1 corrects straight-line direction, defines yield-application
conventions, requires clean-cost and exact-scope assignment authority, and makes unsupported profiles
park explicitly. Its straight-line recurrence allocates the remaining unrecognized adjustment over
the current and remaining authoritative schedule weight, preventing over-amortization as the
denominator declines. The RFC ledger now reports this work truthfully as `target_state`; capability
docs and wiki remain `target_not_implemented` until the runtime is complete.

The transaction-processing domain now owns a framework-independent amortized-cost policy vocabulary.
It validates method/convention compatibility, policy identity and version, fee treatment, and
residual tolerance fail closed. Premium, discount, and par direction is derived from governed
opening book cost and redemption value rather than broad instrument labels. This is an additive
foundation only; it does not promote amortized cost to a supported runtime capability.

The same domain package now owns a pure, deterministic schedule kernel for straight-line and
effective-yield evolution. Straight-line schedules allocate the remaining premium or discount by
authoritative period weight and absorb only the final governed residual. Effective-yield schedules
distinguish annual-effective, annual-nominal-simple, and supplied per-period rates; ambiguous or
missing rate authority fails closed. Every normalized period row and reconciled schedule is bound
to complete input, policy, calculation, output, and numeric-policy lineage. The kernel supports
negative yields greater than negative one, irregular periods, fees-in-basis policy, and replay
identity. Runtime bookability and public contracts remain deliberately unchanged.

The domain now also owns exact source-lot assignment, basis, schedule, and yield facts plus a
fail-closed resolver across tenant, legal book, portfolio, security, lot, and effective date.
Missing, overlapping, conflicting, stale, or convention-incompatible authority does not fall back
to broad instrument classification. Duplicate-version conflicts are validated before newest-source
selection, so resolution is independent of delivery order. Immutable active or parked profiles bind source references,
calculation lineage, deterministic content hashes, and every normalized period.

Additive `lot_amortized_cost_profiles` and `lot_amortized_cost_periods` tables preserve that evidence
without overwriting `position_lot_state` original/tax basis. An application port and SQL adapter use
a stable transaction advisory lock, contiguous append versions, exact-retry neutrality, one bulk
period write, tenant-safe latest/as-of reads, and fail-closed header/period reconstruction. Monetary
outputs are canonicalized to the governed scale before hashing; derived year fractions and rates
remain exact-unbounded because truncating working-precision evidence would invalidate lineage.
Composite portfolio-book and source-lot foreign keys prevent cross-book or cross-security scope
fabrication even through direct database writes.
The open-lot projection now keeps accounting carrying amount in independent local/base fields.
Disposal projection and basis-only mutations change or retain that accounting carry without
rewriting `lot_cost_local` or `lot_cost_base`, which remain strategy/tax acquisition basis. The
additive migration backfills complete pre-existing carry rows from their former combined amounts
and restores the separate FIFO tax basis pro rata from the source BUY's authoritative local/base
acquisition cost. It fails closed before rewriting any row when that source evidence is missing,
non-BUY, incomplete, inconsistent with the open quantity, or followed by a zero-quantity
`SPIN_OFF`/`DEMERGER_OUT` basis transfer that cannot be reconstructed from the legacy combined
state. Its downgrade first restores accounting carry to the legacy combined lot-cost representation so
rollback cannot silently substitute a divergent tax basis for carried book economics. A missing
effective profile now also fails closed whenever a consumed source lot already has persisted carry.
Carry decoration uses a detached open-lot snapshot, so a later profile gap or transaction
validation failure cannot leak a partially applied accounting overlay into its input calculation.
Production certification still requires protected-PR and exact-main evidence tracked by #903/#478,
so schema separation alone does not claim complete fixed-income lifecycle support.
The query read plane now exposes the latest immutable lot-disposal receipt through a
transaction-neutral endpoint. One bounded SQL query selects the latest receipt version and ordered
allocations, including hash-chain, source-lot, calculation-lineage, and amortized-cost authority
evidence. Persistence-neutral immutable read records prevent ORM models escaping the repository.
The amortized allocation projection is lossless: it returns the persisted currency, profile and
recognition identity, original/open/residual quantities, scheduled/current/residual carrying costs,
book FX rate, retained rounding residuals, and calculation lineage already bound by the allocation
hash. The repository reconstructs and verifies that closed evidence before mapping, so an
accounting-control consumer can reproduce the receipt without direct database access and tampered
evidence fails before response assembly.
Existing SELL-specific projections remain compatible; redemption, transfer, and
corporate-action support do not require new family-specific receipt APIs.
Basis-only `SPIN_OFF` and `DEMERGER_OUT` processing no longer discards the per-source-lot
carrying-basis deltas that it applies. FIFO and AVCO emit the same conserved, ordered domain result
with the source lot and acquisition identity plus the canonical target transaction and target lot.
The result is transported through the cost-basis calculation boundary; missing target identity fails
before source-lot mutation.

That basis-transfer evidence is now durable in separate append-only receipt and allocation tables;
it is not aliased into disposal evidence because quantity is retained while basis moves to a target
lot. Exact retries are neutral, changed evidence appends a new version, removed evidence appends a
VOIDED version, and later reactivation remains auditable. Source-lot allocation hashes, semantic
hashes, version hashes, and immediate-predecessor links are verified on reconstruction. The target
transaction and deterministic target-lot identifiers deliberately remain governed references
rather than foreign keys because the valid source-out leg can be processed before the target-in leg.
The transaction-processing unit of work persists these receipts before open-lot and checkpoint
writes, retaining atomic rollback.

The query read plane now exposes the latest receipt at the distinct source-owned
`lot-basis-transfer-receipt` endpoint. One bounded query selects the latest scoped version, its
ordered source allocations, and its immediate predecessor. The query fails closed on identity,
lifecycle, allocation-count, ordinal, uniqueness, local/base conservation, child-hash,
semantic-hash, version-hash, or predecessor-chain mismatch. Its response includes source and target
references, pre-transfer/transferred/retained economics, calculation lineage, and hash-chain
evidence without claiming a target security identifier that the source event does not own.

Quantity-consuming `MERGER_OUT`, `EXCHANGE_OUT`, and `REPLACEMENT_OUT` receipts now carry a
discriminated `INTERNAL_LOT` destination on the receipt header. The destination binds the governed
target transaction, its deterministic `LOT-{target_transaction_id}` lot identity, and the target
instrument while the ordered allocation children retain source-lot ownership. Persistence and the
existing transaction-neutral query expose this source-to-target evidence additively, and receipt
hash reconstruction rejects a missing discriminator, mixed internal/external shape, changed target
identity, or an external reference grafted onto an internal transfer. No target foreign key is
introduced because source-before-target processing is valid. `TRANSFER_OUT` now requires exactly
one destination: the same explicit internal target identity or a canonical opaque
`external_destination_reference` carried through ingestion, event, booked-domain, transaction-ledger,
and query contracts. External transfer evidence never fabricates an internal transaction, lot, or
instrument. Quantity-consuming merger, exchange, and replacement groups now use one domain-owned
reciprocal-leg policy across every supported pair. It verifies source/target transaction type,
two-way transaction reference, and source/target instrument identity independently of input order.
The existing corporate-action reconciliation adapter loads the linked group once, distinguishes
quantity-transfer evidence from Bundle A evidence, and persists deterministic support findings for
missing or inconsistent legs. When a valid source-before-target sequence later becomes complete,
one set-based update resolves superseded open findings with actor and timestamp evidence before the
current result is stored. A PostgreSQL exchange lifecycle proves the initially incomplete group,
final balanced group, resolved finding history, source-lot allocation, target-lot materialization,
and duplicate neutrality together. The same-pattern scan covers merger, exchange, and replacement;
partial internal `TRANSFER_OUT` proof remains open because portfolio-transfer reciprocity is not a
corporate-action linked-group contract.
An additive `lot_amortized_cost_authority` ledger and application port now persist and reload all
four required source families through one governed pattern. Per-source transaction locks,
monotonic correction versions, exact-retry neutrality, canonical decimal/date payloads, composite
book/lot foreign keys, and reconstruction hash verification prevent delivery-order or tampering
drift. The application writer deduplicates and orders atomic caller batches before persistence.
The profile materializer acquires the profile lock before reloading source history, skips unchanged
authority, appends corrected active profiles contiguously, and records missing/conflicting inputs as
parked evidence without invented economics. Parked decision identity includes the complete policy
definition and resulting eligibility reason as well as source authority, so a policy correction
cannot retain an obsolete parked reason as an unchanged profile. Active decision identity likewise
binds the complete policy definition, normalized freshness cutoff, algorithm version, and numeric
output-policy identity, preventing changed calculation semantics, precision policy, or acceptance
thresholds from retaining obsolete economics.
Authority appends acquire that same scope/profile lock before their narrower per-source lock, so a
correction cannot commit between the materializer's source reload and profile decision.
Atomic authority batches sort by that lock scope before authority family and source version.
Authority payloads and profile source-reference/calculation-lineage evidence use PostgreSQL
`JSONB`; the successor authority migration converts already-deployed profile `JSON` columns on
upgrade and restores them on downgrade. This eliminates ambiguous duplicate-object members before
typed reconstruction and canonical-record verification without rewriting applied migration truth.

Source-owned ingestion contracts, the production Kafka consumer and unit-of-work composition, and
the public effective-as-of query are now implemented foundations. The delivery boundary validates
the governed event envelope before domain construction. Correction handling separates the
stream-global version head from exact-boundary idempotency, then atomically rebuilds the corrected
boundary and every persisted later boundary in chronological order. Policy assignment is resolved
again at each boundary, and any later-boundary failure rolls back the authority event transaction.
Assignment corrections that move `valid_from` now enumerate from the earlier of the previous and
current assignment boundaries. The superseded earlier boundary is therefore rematerialized as
parked evidence when a corrected assignment moves later instead of retaining obsolete economics.
Persisted query reconstruction integrity, redemption integration, wider runtime recovery/load proof,
and final capability certification remain open.

Correction replay is now active through one bounded source-lot command path. Assignment,
clean-cost-basis, schedule, and yield corrections derive their replay start from the earlier of the
previous and current validity boundaries. The authority transaction stages at most one command
whose hash-bound identity excludes diagnostic correlation metadata. A dedicated ordered consumer
validates the strict event and exact source-lot partition key, then republishes only the earliest
affected booked transaction. The command id becomes the transaction repair-delivery claim, so
Kafka redelivery may republish transport work but cannot repeat financial business work. Because
that booked transaction is older than the current cost-basis checkpoint, canonical processing
loads complete history, recalculates amortized carrying cost and realized P&L, and reconciles the
affected disposal-receipt/open-lot/checkpoint/lineage suffix in one transaction. This avoids one
Kafka command per disposal while retaining deterministic reversal/void evidence.

Protected review found two connected expiry defects before merge. A correction that shortened an
inclusive authority `valid_to` could omit the first inactive day when no later profile boundary
already existed, and the disposal overlay treated a resulting parked decision as though it were an
active profile with missing currency. The handler now materializes the day after both prior and
current expiry boundaries. A durable non-active profile explicitly removes accounting carry and
retains the calculator's original-cost disposal economics; an absent profile still fails closed so
transient or corrupt profile gaps cannot silently unwind financial state.

FIFO and average-cost disposal now return immutable, ordered source-lot allocations while retaining
the legacy aggregate tuple projection. Allocation construction proves exact quantity and dual-
currency cost conservation, binds the source-lot inputs and aggregate output to the governed
numeric policy, and stages only successful positive transaction disposal evidence. The
calculated-output policy inventory was reconciled to the moved allocation call sites so stale proof
references cannot pass protected lint. The application layer now converts accepted disposal
evidence into complete receipt candidates and persists them through the transaction unit of work
before lot-state and checkpoint writes. Additive `lot_disposal_receipts` and
`lot_disposal_allocations` tables retain immutable ACTIVE and VOIDED versions, ordered source
allocations, transaction and calculation lineage, content hashes, and an immediate-predecessor hash
chain. Exact retries are write-neutral; semantic corrections, removal, and reactivation append
auditable versions. Composite foreign keys and reconstruction checks reject cross-book fabrication
and persisted header/allocation tampering. Governed financial-numeric classification covers all six
receipt/allocation measures. Public query and OpenAPI exposure, deep-chain recovery/load proof,
transfer and corporate-action target lineage, and redemption consumption remain open under
#481/#477.
PR review then found that immediate engine recording could expose evidence for a cash-in-lieu
transaction rejected by later allocated-basis reconciliation. Disposal evidence is now two-phase:
the engine stages it during lot consumption, the complete transaction calculator commits it only
after all strategy validation and transaction lineage succeed, and every rejection or exception
discards pending evidence.
AVCO disposal materialization is also bounded to the current open generation. Historical source
identities remain available to explicit state expansion, but repeated buy/full-dispose cycles no
longer rescan closed generations in the calculation hot path.
Pending-disposal commit, discard, and record filtering also normalize transaction identity at the
engine boundary, matching the immutable evidence key and preventing whitespace variants from
leaking staged evidence or suppressing an accepted record.

## Same-Pattern Review

The review covers both remaining `resolve_valuation_unit_price` call sites, authoritative price and
assignment correction paths, valuation receipts and Query projections, FIFO and average-cost lot
disposal, tax-lot consumers, transaction partitioning, linked-leg readiness, correction replay, and
the transaction capability registry. The legacy magnitude heuristic remains confined to explicitly
unscoped history; it cannot govern an authoritative receipt.

## Compatibility And Documentation

Existing unit-price results, snapshot fields, tax/original lot basis, and production-bookable
transaction types remain stable. The lot-disposal query adds nullable destination fields; legacy
receipts preserve their exact semantic hash because absent destination evidence is omitted from the
hashed payload. The transaction contract and ledger add nullable external destination authority;
the lot-disposal allocation response also adds nullable amortized-cost reconstruction fields. These
fields disclose existing persisted evidence and do not change receipt hashes, write behavior, or
legacy non-amortized response values.
`TRANSFER_OUT` without exactly one internal or external destination now fails before persistence by
intent. `FACTOR_ADJUSTED_CURRENT_PRINCIPAL`, supplied current principal,
accrued-income variants without evidence, and every redemption type remain fail closed. The schema
change is additive; no public API/OpenAPI, Kafka runtime, or capability claim changed. The authored
Data Models wiki documents the staged ledgers while the capability wiki remains
`target_not_implemented`.

## Validation

- signed commits `fb558698e`, `2ceec9e34`, `7f76491fe`, `fc79da648`, `47f059684`, and
  `3deb33d9b`;
- 35 warning-strict authoritative valuation tests;
- 49 warning-strict shared valuation/calculator tests;
- 77 warning-strict reconciliation domain/service/repository tests;
- 18 warning-strict amortized-cost policy tests;
- 34 warning-strict fixed-income policy and schedule-kernel tests, including irregular-period,
  premium, discount, negative-yield, rate-authority, date-only input, reconciliation, sub-quantum
  rounding, and lineage proofs;
- 139 warning-strict fixed-income and calculated-output-policy guard tests;
- signed commits `116e8271e`, `5869cb101`, `90ab97c28`, `5ae948013`, `8534f951f`,
  `29fe415df`, `34da8eb92`, and `a0969c741` for source ranking, authority, facts, resolution,
  profiles, schema, precision, and repository controls;
- 94 warning-strict fixed-income domain and adapter unit tests;
- 54 focused migration, ORM, and advisory-lock unit tests;
- 4 real-PostgreSQL profile repository tests covering append/retry, contiguous versions, exact
  as-of selection, and canonical header/lineage/period tamper rejection;
- 95 warning-strict fixed-income domain/migration tests plus 18 application writer/materializer
  tests;
- 17 real-PostgreSQL authority cases covering all four source families, exact retry, monotonic
  corrections, source-version collision, typed reload, payload-shape enforcement at top-level and
  nested schedule-period boundaries, canonical representation and decimal encoding, and
  persisted-payload tamper rejection;
- real-PostgreSQL authority migration apply, constraint, rollback, and reapply proof;
- migration and numeric guards passed at head `c141b2c3d50e`, with 116 governed numeric columns
  across 35 tables and no planned enforcement gaps;
- scoped Ruff lint/format, MyPy, RFC ledger, architecture-documentation, transaction-capability,
  wiki, JSON, calculated-output-policy, and diff-hygiene guards.
- signed correction-hardening commits `0a46043bf`, `03499a2c9`, `ed63915df`, and `9038326cb`;
- 18 warning-strict materialization tests and 9 warning-strict event-orchestration tests covering
  governed envelope validation, exact-boundary replay neutrality, chronological later-boundary
  rebuild, effective-dated policy transitions, and atomic rollback; focused Ruff and MyPy passed.
- signed correction-boundary commit `1ba51ce63`;
- 45 warning-strict fixed-income application tests covering moved-later and moved-earlier assignment
  corrections, exact-duplicate neutrality, superseded-boundary parking, and atomic rollback;
  focused Ruff, format, MyPy, and diff checks passed.
- signed allocation commits `d3192f3c6`, `8c043a15d9`, and `653462a3b` plus the final lineage-guard
  fix-forward commit;
- 194 warning-strict authority and cost-basis allocation tests, plus 113 warning-strict allocation
  lineage and calculated-output-policy guard tests; scoped MyPy, Ruff, JSON, and diff checks passed.
- review fix-forward proof: 103 warning-strict calculator/disposition tests cover accepted commit,
  rejected cash-in-lieu discard, explicit pending discard, filtering, and cleanup; scoped MyPy and
  Ruff passed.
- final AVCO performance fix-forward proof: 201 warning-strict calculation tests include a
  structural closed-generation scan guard; repeated full-close measurements were 0.019s for 100,
  0.038s for 200, and 0.083s for 400 cycles; repository-native MyPy (267 sources), scoped Ruff,
  and diff checks passed.
- transaction-identity fix-forward proof: 104 warning-strict disposition/calculator tests cover
  normalized commit, filter, and discard behavior; repository-native MyPy (267 sources), scoped
  Ruff, and diff checks passed.
- signed receipt-ledger commits `a7b852dfa` through `1a55584a2`; 135 warning-strict focused
  unit/migration/model tests and 3 real-PostgreSQL integration tests cover immutable append, retry
  neutrality, correction, void, reactivation, predecessor/hash verification, allocation-tamper
  rejection, atomic unit-of-work ordering, and initial-void neutrality; repository-native lint and
  MyPy (273 sources) passed.
- signed book-carry separation commits `6643a4773` and `68ceb2786`; 121 warning-strict focused
  domain/application/repository/migration tests cover independent tax and accounting amounts,
  incremental and terminal disposal, basis-only carry retention, persistence reconstruction,
  lineage, and reversible migration; migration smoke, Ruff, and MyPy (275 sources) passed.
- signed correction-replay commits `9a7720e49`, `5879145bb`, `2824e19ff`, and `41e0c3e8a`;
  earlier-boundary coverage spans every authority family, stable repair identity is fail-closed at
  the Kafka boundary, and one-anchor consumer/runtime topology is contract-checked at 12 partitions
  with 12 maximum in-flight messages. Focused evidence includes 67 replay/idempotency tests, 17
  correction event/consumer tests, 65 runtime/configuration tests, 41 amortized-disposal and receipt
  lifecycle tests, 24 real-PostgreSQL authority/profile/receipt cases, focused Ruff, and focused
  MyPy. The 1,001-disposal cohort retains one bulk profile read and no per-disposal command fan-out.
- protected-review fix-forward proof: 44 warning-strict amortized-disposal and authority-event
  orchestration tests cover explicit parked-profile carry unwind plus prior/current day-after-expiry
  materialization; repository-native lint and MyPy (280 sources) passed.
- transaction-neutral receipt query and basis-transfer lineage proof: 222 focused domain,
  strategy, timeline, query-repository, service, and API tests passed. FIFO and AVCO conserve
  pre-transfer, moved, and retained local/base carrying basis per source lot; missing target identity
  is mutation-neutral. Repository-native lint, MyPy (285 sources), numeric-persistence,
  calculated-output-lineage, repository-output-shape, route-family, architecture, OpenAPI, and diff
  guards passed.
- append-only basis-transfer persistence and supportability query proof: 45 focused writer/query
  tests cover exact retry, correction, VOIDED state, reactivation, source-before-target ordering,
  missing allocation rows, allocation tampering, conserved source economics, service mapping, and
  OpenAPI vocabulary, plus 2 real-PostgreSQL cases proving version history and post-restart child
  tamper rejection. Repository-native MyPy passes across 292 source files; scoped Ruff,
  generated route catalog, API vocabulary, OpenAPI, and diff checks pass. Remote Feature Lane
  `30901770196` is green at exact predecessor head `94687ceaef` across all five jobs. The authored
  capability wiki remains unchanged because complete corporate-action scenario certification and
  production redemption are still open.
- quantity-consuming destination proof: signed commits `1f3139c16` through `ad7f7a133`; 27 focused
  domain, adapter, application, and query tests cover internal/external discrimination, exact legacy
  hash compatibility, persistence reconstruction, destination tamper rejection, required target
  identity, and additive response mapping. The exact-source PostgreSQL full-exchange scenario passed
  in 428.82 seconds with migration head `c147b2c3d514`, source allocation, duplicate neutrality, and
  target transaction/lot/instrument evidence. Remote Feature Lane `30903554727` is green across all
  five jobs at predecessor head `3edfdac9f`; exact-current-head CI remains pending.
- external-transfer destination proof: migration head `c148b2c3d515` adds nullable transaction
  authority; 17 focused application tests cover internal, external, missing, partial, ambiguous, and
  wrong-family destination shapes. The exact-source PostgreSQL external-transfer lifecycle passed in
  417.67 seconds, proving the opaque event value persisted on the transaction and receipt, the
  source lot was fully consumed without realized P&L, and no internal target identity was invented.
  Migration, OpenAPI, API-vocabulary, Ruff, format, and focused mapping checks pass. Reciprocal
  validation for internal legs processed on distinct streams remains open under #481.
- partial internal-transfer proof: signed commit `e811398d3` adds an exact-source PostgreSQL
  lifecycle across distinct source and target portfolios. Moving 40 of 100 units transfers exactly
  400 of 1,000 local/base basis, leaves the source lot at 60/600, creates the target lot at 40/400,
  records the reciprocal transaction/lot/instrument destination and ordered source allocation, and
  emits no realized capital or FX P&L. Exact duplicate delivery is neutral. The integration proof
  passed in 37.26 seconds; nine focused destination/transfer unit cases also passed. This closes the
  partial-transfer scenario required by #481 without claiming #476's complete pair-query,
  restatement, FIFO/AVCO matrix, or the reusable parent/dependency graph retained by #480.
- production redemption proof: signed commits `4eef191d1` through `2a4bb0ea8` promote maturity,
  call, and partial redemption through the canonical registry/calculator, add reversible
  `c149b2c3d516` investment-inflow rules, and persist generated economic-event/group identity on
  both product and principal-cash legs. Five exact-source PostgreSQL lifecycle/rule cases passed in
  35.78 seconds, proving full and factor-based partial lot depletion, local/base basis, principal-only
  capital/FX P&L, equal non-coupon cashflows, immutable allocations, and duplicate neutrality. A
  warning-strict 1,000-redemption cohort passed for FIFO and AVCO in 1.86 seconds with exactly one
  source allocation per event and terminal 1,000/970 conservation. The separate accumulating-source
  AVCO profile remains open under #481: FIFO 8,000 completed in 2.140657 seconds while AVCO 1,000
  required 20.662403 seconds because proportional source evidence expands across every active buy.
- replay-determinism proof: signed commits `56b1a0a93` and `ff4a95918` canonicalize transaction-cost
  and disposal-allocation lineage at the governed ledger scale, exclude persistence- and
  settlement-owned generated fields, and advance both changed algorithms to version 2. A focused
  unit pack passed 126 warning-strict cases. Exact-source PostgreSQL replay restored the deleted
  product and principal cashflows in 29.76 seconds while retaining exactly one immutable disposal
  receipt version and one allocation; the complete four-case redemption lifecycle pack passed in
  44.99 seconds. Repository-native lint and every composed governance guard passed, and full MyPy
  reported no issues across 292 source files. The compatibility impact is intentional and bounded:
  lineage hashes/version change where the canonicalization contract changed; financial amounts,
  booking contracts, schema, API/OpenAPI, Kafka topology, and settlement identities do not.
- protected-review and coverage proof: registry-owned cash-entry defaults now prevent non-zero
  redemption booking without a settlement account, while canonical zero-price/zero-proceeds
  write-offs are accepted at ingestion with truthful zero gross proceeds and create no synthetic
  cash adjustment. Ordinary transaction families retain their strictly positive gross-amount
  contract; OpenAPI documents the non-negative transport boundary and conditional family rule.
  Tolerance-close maturity/call quantities consume
  the exact available position. Query-side disposal and basis-transfer verification has 100% line
  and branch coverage across 252 statements and 146 branches; 253 focused registry, preparation,
  settlement, redemption, cashflow, and query-repository tests pass. Repository-native Ruff, full
  MyPy (292 sources), calculated-output-policy, and diff guards pass. Protected exact-head rerun and
  merge evidence remain recorded through PR #910 and issue #477 rather than duplicated here.
- late-review cashflow hardening: redemption product cashflows are settlement-dated and carry the
  net principal component; non-zero embedded accrued interest produces a deterministic linked `INTEREST`
  component with its own `INCOME` cashflow and lineage, while the generated adjustment remains the
  sole net settlement cash authority. Ingestion now rejects missing, partial, mixed, or unrelated
  transfer destinations. Exact-zero net redemption settlement omits a synthetic adjustment and
  negative settlement still fails closed. Linked upstream interest plus embedded redemption
  interest fails before mutation, with canonical generated components excluded during replay.
- final protected-review hardening: a zero quantity accompanied by factor authority is treated as
  the ingestion transport placeholder for absent explicit redeemed quantity; complete old/new
  factors derive the quantity, while non-zero dual authority must still reconcile. Linked-interest
  ambiguity is evaluated through one indexed portfolio/group read across instrument and security
  boundaries before mutation; those group rows never enter security-scoped cost-basis rebuild
  history. A positive accrued-interest component may carry no cash-link identity only when the
  canonical net settlement is exactly zero, preserving income evidence without inventing a zero
  adjustment. Negative settlement and unlinked non-zero settlement remain rejected. Consolidated
  proof: 177 unit cases, 4 exact-source PostgreSQL redemption lifecycle cases, Ruff/format/diff,
  full MyPy across 294 source files, and the composed architecture guards pass. No API, OpenAPI,
  schema, migration, Kafka, capability, central-context, skill-routing, or additional wiki truth
  changed.
- final boundary proof: registry-derived ingestion rules require complete target transaction and
  instrument destinations for `MERGER_OUT`, `EXCHANGE_OUT`, and `REPLACEMENT_OUT` before job
  creation or publication, while partial-basis spin/demerger and transfer-out external-destination
  contracts remain unchanged. The basis-transfer supportability reader now strictly reconstructs
  transaction and transfer lineage, verifies the closed algorithm/numeric-policy identity, and
  binds active lineage to persisted source allocations and aggregate outputs. Writer and reader
  share one canonical payload contract to prevent drift. Validation: 334 ingestion/router cases,
  118 writer/reader unit cases, query verifier 100% line/branch coverage across 99 statements and
  52 branches, full MyPy, and architecture guards pass. No OpenAPI shape, schema, migration, Kafka,
  capability, central-context, skill-routing, or additional wiki truth changed.
- final receipt-integrity proof: the signed redemption principal component determines its cashflow
  classification after settlement deductions, so an economically negative component is an
  `INVESTMENT_OUTFLOW` while separately linked accrued interest remains `INCOME`; the components
  still reconcile exactly to authoritative net settlement. Disposal supportability now verifies
  that calculation lineage binds every persisted source allocation and the aggregate consumed
  quantity, local cost, and base cost. The producer and reader share one versioned canonical
  payload contract, preventing independent serialization drift. No API/OpenAPI shape, schema,
  migration, Kafka, capability, central-context, skill-routing, or additional wiki truth changed.
- correction-child proof: correction-only reconciliation now resolves deterministic generated
  cash and accrued-interest children for the corrected source transaction. A child no longer
  justified by corrected economics is identity-validated, persisted as zero-valued superseding
  evidence, and emitted through the established position/cashflow repair path. Cleared product and
  component links are explicitly persisted as SQL `NULL`, avoiding sparse-upsert retention of stale
  references; ordinary bookings incur no new child reads. Exact-zero `UPSTREAM_PROVIDED` redemption
  may truthfully omit a cash-leg
  reference, while explicit zero adjustments and non-zero missing pairs remain rejected. No
  API/OpenAPI shape, schema, migration, Kafka, capability, central-context, skill-routing, or
  additional wiki truth changed.
- correction field-presence hardening: semantic correction now owns one explicit set covering
  nullable redemption price type, factor bounds, principal, accrued interest, embedded fee, and
  embedded tax. Cost persistence writes every member for a redemption rebuild, including SQL
  `NULL` when the corrected command omits prior authority, while non-redemption sparse updates stay
  unchanged. A correction with positive interest but zero net settlement loads the prior interest
  child, retains the income component, and clears its retired cash/component links. Validation:
  41 warning-strict unit cases and one two-repair PostgreSQL lifecycle passed in 70.17 seconds,
  covering positive-to-omitted, positive-to-zero, cash retirement/regeneration, and durable rows.
  No API/OpenAPI, schema/migration, Kafka, generated identity, or ordinary-booking query change.
- final redemption-contract proof: all three production redemption commands require a source-owned
  settlement date at ingestion, canonical-event, preparation, and cost-domain boundaries, blocking
  every fallback from trade date to cash value date. Before lot access, the cost domain requires a
  closed, command-aware fixed-income product classification and rejects missing, equity, generic
  structured-product, contradictory asset-class, and perpetual-maturity classifications. This is
  product-family eligibility only; issuer schedules and entitlement determination remain upstream.
  No schema, migration, Kafka topology, capability promotion, central-context, skill-routing, or
  additional wiki truth changed.
- protected runtime query proof: additive redemption columns pushed the schema-derived transaction
  evidence payload beyond PostgreSQL's 100-argument function limit, causing the transaction-ledger
  endpoint to return HTTP 500 and cascading into Docker smoke, latency, canonical validation, and
  E2E failures. Evidence payloads are now assembled as bounded JSONB-array chunks and concatenated
  into the same flat array before hashing, so every ledger field remains bound without changing the
  digest algorithm. The same helper governs transaction, cost, cashflow, and FX evidence as their
  schemas evolve. Validation: 25 focused repository unit cases and four real-PostgreSQL evidence,
  mutation, snapshot, and session-format cases pass; the exact Docker endpoint smoke passes 66
  assertions with zero failures. No API/OpenAPI shape, schema, migration, Kafka, capability,
  central-context, skill-routing, or wiki truth changed.

Protected PR and exact-main evidence remain pending for this tranche. Wider runtime recovery/load
proof, complete corporate-action scenario coverage, redemption, and final issue closure remain
pending until their corresponding implementation slices exist. No
capability-wiki promotion is warranted because fixed-income lifecycle support is not yet
production-certified.
