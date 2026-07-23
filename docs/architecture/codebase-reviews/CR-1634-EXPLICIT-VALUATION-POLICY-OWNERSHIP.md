# CR-1634: Explicit Valuation Policy Ownership

## Objective

Replace implicit position-valuation scaling with an explicit, framework-independent policy contract
that position valuation and financial reconciliation can apply identically without either service
importing the other's implementation.

## Finding

The shared valuation-unit-price helper still infers legacy bond quote scaling from product type,
price magnitude, quantity, and average cost. That inference cannot represent clean versus dirty
percent-of-principal quotes, factor-adjusted principal, listed-contract deliverables, supplied
per-contract or whole-position fair value, or the distinction between futures notional and supplied
settlement variation.

The calculation semantics have two legitimate deployable consumers: position valuation produces
the financial result and financial reconciliation independently reproduces the expected result.
Keeping separate copies would recreate methodology drift; placing the policy in either service
would create a cross-service implementation import. Under repository rule 155 and CR-1517, the
narrow framework-free contract therefore belongs in `portfolio_common.domain.valuation`.
`portfolio_common` remains a distribution boundary, not a default architecture layer.

## Change

- Added composable policy/value objects for input basis, principal basis, position scaling,
  accrued-income treatment, FX conversion, and output measure.
- Added one deterministic calculation result that keeps clean value, accrued income, total market
  value, notional exposure, and settlement variation distinct.
- Added an immutable registry of 22 supported version-1 policy compositions. Resolution requires an
  exact policy identifier and version; there is no product-class, latest-version, or default-policy
  fallback. Percent-of-principal variants declare face, factor-adjusted, or supplied current
  principal and calculated or supplied accrual explicitly, while futures notional and settlement
  variation cannot resolve as market value.
- Added explicit no-periodic-accrual clean-price compositions for face, factor-adjusted current
  principal, and supplied current principal. These support zero-coupon/stripped discount positions
  without applying a coupon formula; discount accretion, effective-interest, and tax amortization
  remain outside the position market-value kernel.
- Added explicit calculated ex-coupon compositions for face, factor-adjusted current principal, and
  supplied current principal. A source-owned entitlement carries the ex-date, next payment date,
  full coupon segments, and source lineage. Settlement must fall strictly inside the supplied
  ex-period; the elapsed calculation must be an exact economic prefix of the full coupon. Core
  recalculates both under the same 50-digit segmented kernel and exposes gross accrual, the signed
  full-coupon entitlement adjustment, and settlement accrued income separately.
- Implemented the DMO rebate-interest convention as signed elapsed gross accrual minus the signed
  full next coupon. Long ex-coupon positions therefore produce negative rebate interest, short
  positions reverse the sign, and settlement on or before the ex-date fails closed for this policy.
  Ex-period determination remains source-owned and is never inferred from product class or a local
  holiday calendar.
- Added immutable, tenant/legal-book/instrument-scoped valuation-policy assignments with exact-scope
  effective-date resolution, source-version fencing, overlap and gap rejection, deterministic
  content hashing, complete cache identity, and bounded replay-date derivation for corrections.
- Conflicting payloads that claim the same source record and assignment version fail closed instead
  of being selected by arrival time or a lexical source revision.
- Reused the financial canonical-content normalizer for assignment/cache hashes, deleting a second
  hand-built JSON/SHA-256 path and ensuring equivalent aware observation instants have one UTC-
  canonical assignment identity.
- Added reversible persistence for source-versioned valuation-policy assignments. The table keeps
  tenant, legal book, instrument, policy, effective interval, lifecycle, source revision,
  observation time, and assignment reason as separate facts; database checks enforce governed
  lifecycle and positive versions, while partial effective-scope and descending source-history
  indexes support deterministic resolution without a product-class fallback.
- Added an exact-scope market-price source-fact contract and separate reversible append-history
  table. Domain resolution ranks positive source correction versions before lifecycle, so a later
  suspension/retirement fences older ACTIVE facts; missing, same-version conflicting, and competing
  source authority fail closed. Stable correction identity is source system/record/version, while
  tenant, legal book, instrument, and business date are versioned authority payload; each row keeps
  explicit unit, clean-percent, or dirty-percent representation, exact unbounded numeric
  value/currency, lifecycle, source revision/content hash, and aware observation time. The database
  does not impose an undeclared decimal precision/scale that could corrupt correction replay.
- Kept the global `(security_id, price_date)` `market_prices` projection unchanged. The new
  authority table has no mutable update timestamp. Its scope-history index finds candidate source
  identities and its globally unique source-version key supports latest correction ranking before
  exact-scope/lifecycle selection. Production valuation, reconciliation, query, freshness, demo,
  and replay readers remain legacy until a later coordinated cutover.
- Added a dedicated insert-only writer that locks stable source identities before sorted old/new
  authority identities, no-ops exact durable replay, rejects divergent same-version or stale
  corrections, validates current ACTIVE claims after ranking complete candidate histories, and
  returns both previous and accepted authority identities for downstream invalidation/replay.
  Write batches fail closed above 500 records and history predicates use 100-key chunks.
- Added a position-valuation-owned bulk read port and SQLAlchemy adapter. Each bounded query uses
  scope history to find candidate sources, ranks the globally latest source version in SQL, and
  applies exact current scope/date only after ranking; framework-independent resolution then fails
  closed on missing or overlapping ACTIVE authority without per-position reads. Read batches also
  fail closed above 500 requests and execute deterministic 100-key query chunks.
- Added a dedicated ingestion contract for authoritative valuation-policy assignments instead of
  extending the legacy reference-data DTO module. It trims source identifiers, resolves an exact
  supported policy/version, rejects naive observation timestamps, invalid windows, duplicate
  source versions, oversized batches, and overlapping active authorities without deriving legal
  book from booking centre or jurisdiction.
- Added a service-owned transactional write guard that acquires exact tenant/legal-book/instrument
  advisory locks in stable order, loads durable assignment history, ranks source corrections, and
  rejects conflicts before one atomic upsert/commit. This closes both the existing-history and
  concurrent-writer gaps that request-only validation would leave open.
- Added a position-valuation-service application port and SQLAlchemy resolver for durable assignment
  history. One indexed query ranks each source record's correction versions before applying ACTIVE
  lifecycle and inclusive effective-date filters, then the framework-independent domain rejects a
  missing or overlapping authority and the exact-version registry rejects an unsupported policy.
  The returned runtime value binds the resolved assignment/cache identity to the executable policy;
  persistence and query construction remain service-local rather than moving into
  `portfolio_common`.
- Added the first versioned day-count registry slice for FpML/ISDA `ACT/365.FIXED`, `ACT/360`, and
  `BUS/252`. Fixed-denominator conventions use actual elapsed calendar days. `BUS/252` counts
  source-owned business dates start-inclusive and end-exclusive and requires a versioned calendar
  whose validity covers the calculation interval; it never substitutes weekdays or a local holiday
  guess.
- Added `30/360.US`, `30E/360`, and `30E/360.ISDA` as separate exact conventions rather than
  aliases. The U.S. convention applies the SIFMA end-of-February and 31st-day sequence; Eurobond
  basis adjusts 31st dates only; ISDA basis adjusts month ends while preserving a February
  contractual termination date and therefore requires that source fact.
- Added `ACT/ACT.ISDA` using actual elapsed days split by each calendar year's 365/366 denominator.
  Added `ACT/ACT.ICMA` only with authoritative regular or quasi-coupon reference periods: each
  overlap is divided by that reference period's actual days and contractual coupon frequency, and
  missing, gapped, or overlapping reference coverage fails closed. This supports regular, short-
  stub, and long-stub calculations without generating an implicit schedule.
- Added gross contractual accrued-income calculation over contiguous segments carrying explicit
  signed principal, fixed or upstream-supplied floating all-in annual rate, day-count policy, and
  separate rate/principal/schedule lineage. Principal changes and rate resets accrue on their own
  intervals; gaps, overlaps, mixed currencies, non-finite values, missing lineage, and unsupported
  conventions fail closed. Zero and negative contractual rates and short principal retain their
  source sign.
- Fixed day-count and accrual intermediate precision at 50 decimal digits inside local Decimal
  contexts so repeating fractions and aggregate results do not depend on ambient process precision.
  Rounding remains a separately governed persistence/API boundary.
- Advanced the accrued-income lineage algorithm to version 2. Its input now binds any entitlement
  source, ex-date, next payment date, and complete coupon-period segments; its output binds gross
  accrual, entitlement adjustment, and settlement accrual as distinct figures. The elapsed/full-
  coupon consistency check is a linear ordered pass over immutable terms, avoiding nested scans or
  repeated source-payload construction on the high-volume calculation path.
- Added reusable deterministic calculation lineage with separate input, calculation, and output
  SHA-256 hashes. Calculation identity binds algorithm ID/version and intermediate precision to the
  canonical input hash; output identity binds named result values to the calculation hash. Decimal,
  dates, UTC-normalized aware timestamps, enums, mappings, sequences, and sets normalize
  deterministically, while floats, non-finite values, naive timestamps, ambiguous keys, and
  unsupported objects fail closed.
- Attached the three-layer lineage to segmented accrued-income results. Each source reference now
  carries an immutable source-content hash and aware observation timestamp; calendar-backed inputs
  bind a precomputed calendar-content hash. A corrected source revision changes every downstream
  lineage layer even when the monetary amount remains equal, while caller segment order does not
  alter the canonical result.
- Business-calendar content hashing occurs once when the immutable calendar is constructed, not
  once per accrued-income calculation, preserving deterministic evidence without introducing
  business-date serialization on the high-volume per-position path.
- Consolidated source-system/record/revision/content-hash/observation evidence into one immutable
  financial source-reference value shared by accrued income and position valuation; the existing
  accrued reference name remains an alias rather than a duplicate structure.
- Attached the same three-layer lineage to the complete position-valuation result. Input identity
  binds the exact policy composition, assignment source, and only the price/value, currency,
  position/principal/factor, multiplier, derived-or-supplied accrued income, and direct FX evidence
  consumed by that policy. Output identity keeps clean value, accrued income, total market value,
  notional, settlement variation, current principal, and local/reporting amounts distinct.
- Fixed position-scaling, aggregation, and FX conversion to a 50-digit local Decimal context. A
  regression test caught reporting-currency conversion escaping the context; both returned values
  and output lineage now use the identical fixed-precision results.

## Ownership Boundary

Only immutable valuation vocabulary, value objects, calculation policy, and deterministic assignment
resolution belong in the shared domain package. The position-valuation service owns the runtime
resolution port and SQLAlchemy query adapter. Ingestion DTOs, assignment persistence, approval and
migration workflows, impact previews, replay scheduling, caches, Kafka adapters, API contracts, and
service orchestration remain with their owning deployables. Before runtime wiring, production
consumer imports must prove the shared boundary; if only one deployable consumes a policy, move it
to that service's domain package.

## Compatibility

The assignment slices add one reversible table, two evidence-backed indexes, one source-write
HTTP/OpenAPI contract, and one internal service-local read port/adapter. Existing routes, event
payloads, topics, deployment topology, downstream fields, and runtime valuation behavior were
unchanged by those slices. A subsequent staged prerequisite adds nullable `tenant_id` and
`legal_book_id` together to portfolio ingestion, events, and persistence. Both absent preserves
legacy compatibility and cannot erase an established persisted scope during replay; a complete
incoming pair replaces both dimensions atomically. Partial, blank, padded database-direct, or
non-string authority fails closed.
The market-price authority slice adds a second reversible history table, an internal insert-only
write boundary, and a position-valuation-owned bulk resolver without changing the legacy
projection, existing ingestion/event/API contracts, or any runtime consumer. It is a migration
primitive, not permission to reinterpret historical global prices as tenant-safe facts.
Existing correct unit-price behavior is characterized under an explicit policy. The legacy bond
heuristic remains in the runtime path until authoritative market-price persistence and both
valuation consumers are wired; it will be deleted rather than retained as a fallback then.

## Validation

- 102 valuation-domain tests passed, including unit/NAV, clean, dirty, explicit no-periodic-
  accrual percent-of-principal,
  DMO-style long and short ex-coupon rebate interest, ex-date/payment boundary rejection,
  full-coupon economic-prefix rejection, entitlement-source correction lineage,
  factor-adjusted principal, per-unit/per-contract/whole-position supplied values, futures notional,
  settlement variation, FX direction, exact tenant/book/instrument assignment resolution,
  source-version fencing, overlap/gap rejection, conflicting-version rejection, UTC-canonical cache
  identity, backdated replay-date derivation, registry uniqueness, exact-version lookup, derivative
  output separation, position source-revision lineage, missing consumed-evidence rejection,
  fixed-precision position/FX conversion, leap-day fixed-denominator examples, business-day boundary
  semantics, calendar coverage, U.S./Eurobond/ISDA month-end and February behavior,
  contractual-termination handling,
  ISDA leap/non-leap year segmentation, ICMA regular/short/long reference-period cases, ICMA
  gap/overlap rejection, exact day-count convention/version lookup, fixed and supplied-floating
  segment accrual, principal/rate changes, sign handling, lineage/currency/continuity rejection,
  and ambient Decimal-precision independence.
- PR review challenged the February-to-February result for `30/360.US`. The primary SIFMA sequence
  confirms that only a 31st end day is adjusted after the start-day rules; a last-of-February end is
  not rewritten. A 2024-02-29 to 2025-02-28 `358/360` golden vector and explicit methodology text
  now prevent a different 30/360 variant from being introduced under the existing policy identity.
- Lineage tests prove mapping/set order independence, bounded hash impact for input versus algorithm
  versus output changes, valid digest shape, source-revision sensitivity despite amount equality,
  equivalent-instant timezone normalization, calendar-content sensitivity, and rejection of
  ambiguous value types/metadata.
- Scoped Ruff lint and formatting passed.
- Strict MyPy passed for all seven valuation-domain source modules and the focused position test.
- The persistence contract passed 35 focused domain/model/migration tests under the warning gate;
  Alembic reports the new revision as the single head and the repository migration contract accepts
  the exact `c115b2c3d4f4 -> c116b2c3d4f5` reversible edge.
- The ingestion slice passed 68 focused contract tests under the warning gate, including request,
  write-guard, command/error mapping, registry, service, and three ASGI/OpenAPI proofs. Two real
  PostgreSQL tests passed after exact migration upgrade, downgrade, and re-upgrade; they proved
  durable-overlap rejection rolls back without inserting a second authority, a source-versioned
  retirement plus replacement commits as three auditable history rows, and concurrent writers
  serialize to one winner and one conflict without deadlock.
- The service-local resolution slice passed 31 warning-strict assignment, registry, and adapter
  tests. Adapter tests prove one SQLAlchemy round trip, correction ranking by source-record identity,
  exact scope normalization, cache/source-revision evidence, and fail-closed missing, overlapping,
  blank-scope, and unsupported-version cases. One isolated PostgreSQL test proved correction ranking
  occurs before lifecycle/effective filtering, a suspended latest source version cannot revive its
  older ACTIVE version, an unrelated tenant/book cannot leak into selection, and pre-effective
  dates remain unsupported.
- Signed slice commits and validation evidence are recorded on GitHub issue #788.
- The staged portfolio-authority slice adds warning-strict DTO/event/domain/persistence/ORM and
  reversible-migration tests. Its protected PostgreSQL test downgrades and reapplies the exact
  revision, inspects both column and check-constraint truth, rejects partial/blank/padded authority,
  and accepts both legacy-unscoped and exact-scoped rows.
- The market-price authority domain/model/migration cohort passes under warnings as errors. Tests
  prove exact tenant/book/instrument/date isolation, correction ranking, suspension fencing,
  same-version conflict and competing-source rejection, lifecycle/version hash binding, strict
  correction-version typing, append idempotency, stale/divergent write rejection, old/new
  invalidation identities, bounded correction-ranked SQL, finite database price/observation
  enforcement, write/read ceiling and chunk boundaries, the complete schema constraint set, one
  reversible Alembic edge, and no mutation or index on the legacy projection. Protected PostgreSQL
  migration plus authority tests prove downgrade/reapply, catalog truth, exact high-scale and
  large-value round-trip plus idempotent replay, normalized scope/currency/source/hash constraints,
  positive price/version, governed representation/lifecycle, duplicate source-version rejection,
  moved ACTIVE/SUSPENDED/RETIRED fencing, and concurrent competing-writer serialization.
  Unchanged-source and generated-project teardown evidence is recorded on issue #451.

Primary methodology references for the day-count slice are the
[FpML day-count scheme publication](https://www.fpml.org/specs_news/publication-of-fpml-set-of-coding-schemes-catalog-version-1-121/),
which maps `BUS/252` to ISDA Calculation/252, the
[FpML BUS/252 clarification](https://www.fpml.org/ticket/388/), which specifies business days from
and including the effective date to but excluding the termination date, and the
[ISDA 2000/2006 definitions comparison](https://www.isda.org/a/smMDE/Blackline-2000-v-2006-ISDA-Definitions.pdf)
for `ACT/360`, `ACT/365.FIXED`, `30E/360`, and `30E/360.ISDA`, plus the
[SIFMA standard formulas](https://www.sifma.org/wp-content/uploads/2017/08/chsf.pdf) for the U.S.
30/360 end-of-February and 31st-day sequence. The
[ICMA Rule 251 guidance](https://www.icmagroup.org/assets/ICMA-PMH-Circular-2022-01-FINAL.pdf) and
[FpML day-count scheme](https://www.fpml.org/spec/2000/tr-fpml-1-0-2000-09-25/pdf/tr-fpml-1-0-2000-09-25.pdf)
govern the Actual/Actual ICMA and ISDA distinction and required reference-period semantics.
The UK Debt Management Office
[gilt transaction convention](https://www.dmo.gov.uk/responsibilities/gilt-market/about-gilts/)
and [official formulae](https://www.dmo.gov.uk/publications/gilt-market/formulae-and-examples/)
govern the ex-dividend rebate-interest example and settlement-date boundary used in this slice.

## Documentation Decision

Repository context, the canonical position-valuation methodology, risk-based coverage contract, and
this review ledger change because calculation and evidence truth changed. The methodology labels
the new domain as a runtime migration in progress. The new source-write API updates the generated
route/vocabulary catalogs plus the ingestion, API-surface, and data-model wiki sources. The
service-local resolver does not add another wiki change: it is an internal migration seam and is not
yet invoked by production valuation or reconciliation. The later portfolio-authority prerequisite
updates the generated API vocabulary plus `Data-Models` and `Ingestion-Service` wiki sources because
the additive request/event/schema contract changed. README and supported-feature status do not
change. The separate market-price authority table, internal append writer, and bulk resolver update
repository context, this review record, the ledger, and `Data-Models`; no API/OpenAPI/event or
operator workflow changed. Broader product/lifecycle wiki updates remain required with public
ingestion and runtime cutover.
