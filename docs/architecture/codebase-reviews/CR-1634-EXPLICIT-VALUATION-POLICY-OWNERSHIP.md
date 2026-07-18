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
- Added an immutable registry of 16 supported version-1 policy compositions. Resolution requires an
  exact policy identifier and version; there is no product-class, latest-version, or default-policy
  fallback. Percent-of-principal variants declare face, factor-adjusted, or supplied current
  principal and calculated or supplied accrual explicitly, while futures notional and settlement
  variation cannot resolve as market value.
- Added immutable, tenant/legal-book/instrument-scoped valuation-policy assignments with exact-scope
  effective-date resolution, source-version fencing, overlap and gap rejection, deterministic
  content hashing, complete cache identity, and bounded replay-date derivation for corrections.
- Conflicting payloads that claim the same source record and assignment version fail closed instead
  of being selected by arrival time or a lexical source revision.
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

## Ownership Boundary

Only immutable valuation vocabulary, value objects, calculation policy, and deterministic assignment
resolution belong in the shared domain package. Ingestion DTOs, assignment persistence, approval and
migration workflows, impact previews, replay scheduling, caches, Kafka adapters, API contracts, and
service orchestration remain with their owning deployables. Before runtime wiring, production
consumer imports must prove the shared boundary; if only one deployable consumes a policy, move it
to that service's domain package.

## Compatibility

The two domain slices do not change runtime valuation behavior, HTTP/OpenAPI contracts, event
payloads, database schema, topics, deployment topology, or downstream fields. Existing correct
unit-price behavior is characterized under an explicit policy. The legacy bond heuristic remains in
the runtime path until authoritative representation and assignment facts are available; it will be
deleted rather than retained as a fallback when valuation and reconciliation are rewired.

## Validation

- 62 valuation-domain tests passed, including unit/NAV, clean and dirty percent-of-principal,
  factor-adjusted principal, per-unit/per-contract/whole-position supplied values, futures notional,
  settlement variation, FX direction, exact tenant/book/instrument assignment resolution,
  source-version fencing, overlap/gap rejection, conflicting-version rejection, cache identity, and
  backdated replay-date derivation, registry uniqueness, exact-version lookup, and derivative output
  separation, leap-day fixed-denominator examples, business-day boundary semantics, calendar
  coverage, U.S./Eurobond/ISDA month-end and February behavior, contractual-termination handling,
  ISDA leap/non-leap year segmentation, ICMA regular/short/long reference-period cases, ICMA
  gap/overlap rejection, and exact day-count convention/version lookup.
- Scoped Ruff lint and formatting passed.
- Strict MyPy passed for all three valuation-domain source modules.
- The calculation-kernel commit `608751249` is signed; assignment commit evidence will be recorded
  on GitHub issue #788 after commit.

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

## Documentation Decision

Repository context and this review ledger change because domain ownership truth changed. No API,
OpenAPI, migration, operator workflow, README, supported-feature, or wiki truth changes in these
domain-only slices. Methodology and product/lifecycle wiki updates remain required with runtime and
source-contract implementation under #788.
