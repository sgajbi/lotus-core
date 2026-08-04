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
production activation still requires the correction-triggered replay and downstream certification
tracked by #903/#478, so this schema separation does not claim current-book disposal support.
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
Persisted query reconstruction integrity, current-book disposal allocation, redemption integration,
runtime recovery/load proof, and final capability certification remain open.

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
transaction types remain stable. `FACTOR_ADJUSTED_CURRENT_PRINCIPAL`, supplied current principal,
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

Protected PR and exact-main evidence remain pending for this tranche. Runtime recovery/replay and
load proof, verified query reconstruction, transfer/corporate-action lineage, redemption, and final
issue closure remain pending until their corresponding implementation slices exist. No
capability-wiki change is warranted because fixed-income current-book disposal is not yet
production-certified.
