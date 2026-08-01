# CR-1659: Owner-Specific Financial Numeric Boundaries

## Scope

This review tracks bounded GitHub issue #829 owner-specific numeric work across generic simulation,
transaction cost, cost-basis state, position history, cashflow, accrued income, position and
portfolio timeseries, position valuation, and the shared calculated-output arithmetic and lineage
contracts.

## Findings

- Generic simulation quantity, price, and amount accepted lossy JSON floating-point values and
  values that could not fit the existing `NUMERIC(18,10)` persistence boundary.
- Position-history and cashflow calculations inherited the process-global `Decimal` context and
  could produce scale-amplified values that relied on the final exact bind to reject them.
- The generator-based calculated-output context manager attempted to mutate exception traceback
  state during unwinding, which is incompatible with frozen domain exceptions.
- Cashflow events did not independently enforce the amount storage contract.
- Accrued-income and position-valuation calculations used explicit high-precision arithmetic but
  returned scale-amplified outputs without executing their ledger-output policies.
- Calculation lineage could bind algorithm and intermediate precision but could not distinguish a
  numeric-output policy revision from an unchanged calculation method.
- Canonical cashflow calculation executed a governed output policy but did not retain the policy,
  exact financial inputs, calculation identity, or normalized-output identity on its durable row.
- Valuation receipts and cashflow persistence needed the same strict lineage rehydration boundary;
  keeping separate implementations would allow their accepted payload shapes to drift.
- PR review proved the first cashflow lineage implementation re-summed fee components outside the
  governed Decimal context and represented only the effective FX cash component type. Identical
  economics could therefore acquire ambient-context-dependent hashes, while different booked FX
  product families could lose their distinct source identity.
- Accrued-income segment arithmetic and legacy unscoped valuation still had calculated-output paths
  that were not bound to the named output policy, and legacy valuation receipts could not retain
  calculation evidence even when the output was non-flat.
- PR #855 review found precision-only local contexts still inherited ambient rounding in accrued
  income, position valuation, and their day-count inputs. It also found that a downgrade would try
  to restore the old null-lineage constraint while new legacy rows still contained lineage.
- The remaining transaction-cost, cost-basis-state, position-history, position-timeseries, and
  portfolio-timeseries outputs executed governed arithmetic but did not persist calculation
  lineage. Requiring every helper to emit a receipt would duplicate evidence on hot paths, so the
  guard also needed a statically verified final durable-output boundary.
- PR #877 review found aggregate AVCO transition lineage copied onto individual source rows even
  though its output hash described only the pool checkpoint. It also found lineage-only
  position-timeseries recalculation was discarded when financial values and source timestamps were
  unchanged.
- Final PR #877 review found three remaining trust gaps: transaction lineage omitted the persisted
  cost decomposition outputs, position-history evidence did not bind the exact upstream booked
  transaction receipt, and lot-state receipts did not bind the consuming transition or prior
  durable state. The first call-graph boundary implementation also allowed unrelated same-named
  functions to satisfy declared coverage through ambiguous imports or shared helpers.

## Resolution

- Moved the proven exact Pydantic financial numeric types into `portfolio_common` after a second
  service consumer existed, migrated all existing ingestion owners, and removed the duplicate
  ingestion-local module.
- Added domain-owned simulation validation at both request and application boundaries. Fractional
  values must be lexical decimals; lossless integers remain accepted.
- Added named `position-history-ledger-output@1.0.0` and
  `cashflow-ledger-output@1.0.0` calculated-output policies. Both run intermediate arithmetic in a
  deterministic high-precision local context and normalize once at the durable boundary.
- Made the shared arithmetic-context API return the native decimal context manager so frozen
  domain exceptions retain their identity.
- Applied exact `NUMERIC(18,10)` validation to durable cashflow events.
- Added complete numeric-output policy identity to calculation lineage without changing hashes for
  calculations that do not opt into the new evidence.
- Added named `accrued-income-ledger-output@1.0.0` ownership and activated the existing
  `position-valuation-ledger-output@1.0.0` policy.
- Accrued-income and position-valuation calculations now use deterministic 64-digit working
  precision, normalize once to `NUMERIC(18,10)`, fail before persistence on magnitude overflow,
  and bind policy name/version/shape/rounding into calculation lineage.
- Position valuation normalizes clean value and accrued income before deriving the ledger-bound total,
  so the visible component sum remains exactly equal to total market value after rounding.
- Added a compact versioned inventory for all eight calculated-output policies and a deterministic
  AST guard. It rejects unclassified or stale declarations, literal source/contract drift, blank
  ownership, unused policies, invalid lineage posture, and missing required lineage propagation
  into `build_calculation_lineage` per enclosing callable. Computing and discarding a policy
  identity is not lineage evidence. Extracting an arithmetic or normalization method into a local
  callable alias does not bypass execution tracking. Scope-local overwrites and function-parameter
  shadows invalidate prior aliases, and imported, qualified, or chained constructor aliases remain
  part of declaration inventory discovery. Conditional branches are analyzed from the same incoming
  state and joined fail closed; only an alias identical on every exit can certify later lineage.
  Zero-iteration loop exits, exceptional exits, and non-matching structural-pattern exits follow the
  same rule; `finally` assignments remain visible because they execute on every try exit.
  Execution and lineage must co-occur within a control-flow exit; a lineage-only sibling branch
  cannot certify an output-producing branch. Only the canonical
  `portfolio_common.domain.calculation_lineage.build_calculation_lineage` function, resolved through
  verified direct, assigned, relative, module, or fully qualified aliases, can supply lineage credit.
  Conditional expressions and short-circuit Boolean operands are separate exits. Within protected
  `try` bodies, an exceptional exit between policy execution and later lineage construction remains
  an unbound path even when the normal exit eventually builds lineage.
  Governed execution in predicates, iterators, and match subjects/guards is propagated to every
  corresponding exit. Resolvable positional and keyword-only policy defaults remain associated
  with their governed policy while ordinary caller-supplied parameter shadows stay fail closed.
  Callable and control-flow suites stop at the first guaranteed `return`, `raise`, `break`, or
  `continue`; unreachable lineage construction cannot certify an already returned output.
  Every local name rebound by ordinary, aliased, dotted, or wildcard imports first invalidates
  policy-receiver, lineage-identity, extracted-execution, and canonical-builder evidence. A
  recognized policy or lineage-builder import then installs only its proven binding; wildcard
  imports remain fully fail closed because their exported names are not statically knowable.
- Extended the reusable Query Service calculation-lineage response with a typed optional
  `numeric_output_policy` object. It preserves the complete owner policy identity emitted by the
  domain, rejects blank or contradictory numeric shapes, and publishes the additive contract
  through generated OpenAPI and the governed API vocabulary.
- Made canonical cashflow calculation produce deterministic lineage over its complete booked
  transaction, fee composition, resolved rule/context/epoch, calculation method, and normalized
  output while binding `cashflow-ledger-output@1.0.0`.
- Added nullable `cashflows.calculation_lineage` through migration `c130b2c3d503`, serialized it at
  the repository boundary, and rehydrated it into the typed stored result. Legacy rows deliberately
  remain null; no current-policy identity is inferred for historical evidence.
- Centralized strict persisted-lineage rehydration in `portfolio_common` and removed the duplicate
  valuation-receipt implementation.
- Resolve the lineage fee total inside the same 64-digit arithmetic context as cashflow economics,
  then carry that exact value into the input hash without a second ambient-context calculation.
  Record both the booked transaction family and the effective processing component type so
  `FX_SPOT`, `FX_FORWARD`, and `FX_SWAP` cash components retain distinct source lineage.
- Wired the guard into `make lint`. Every
  exact `path::callable` gap is recorded in the contract, keeping the remaining work visible under
  #829 instead of treating absence as non-applicability.
- Bound accrued-income segment arithmetic and every position-valuation output path to their named
  policy. Legacy non-flat valuation now records deterministic algorithm, consumed-input,
  intermediate-precision, normalized-output, and numeric-policy evidence.
- Added reversible migration `c131b2c3d504` so new legacy non-flat valuation receipts persist that
  lineage while retaining `LEGACY_UNSCOPED` authority semantics. Existing rows and flat,
  quote-independent zero valuations remain explicitly nullable rather than receiving invented
  historical evidence. The inventory now reports three `required`, zero `partial`, and five
  `not-exposed` policies.
- Made every valuation-domain intermediate context specify governed precision and rounding rather
  than inheriting process state. The migration downgrade now removes only newly enriched
  `LEGACY_UNSCOPED` receipts before restoring the prior constraint. Deletion preserves the
  snapshot and avoids retaining either lineage the old schema cannot represent or a receipt hash
  that no longer matches its content.
- Added deterministic typed lineage at each remaining owner boundary: final calculated transaction
  costs, FIFO and AVCO state transitions, position-history rows, position-timeseries rows, and
  portfolio-timeseries rows. Migrations `c134b2c3d507` through `c138b2c3d50b` add nullable JSON
  evidence without inventing receipts for legacy rows. Transaction fees remain atomically replaced
  with their parent cost result, position history retains its ordered chain, portfolio contributions
  are sorted before hashing, and AVCO preserves set-based persistence rather than adding N+1 work.
- Extended the guard contract with optional `lineage_boundary_callsites`. A declared boundary earns
  credit only when static analysis proves that exact callable invokes the governed lineage builder;
  stale or invented boundaries fail closed. The inventory is now eight `required`, zero `partial`,
  zero `not-exposed`, and zero unclassified gaps.
- Kept AVCO numeric scaling set-based, captured pre-transition source states in one ordered read,
  and attached one row-specific receipt to each final managed source row. Each receipt now binds the
  prior source state, pool transition, and exact persisted row output; membership drift fails
  closed. Position-timeseries now upserts a changed receipt independently of numeric restaging, so
  legacy-null or stale evidence is repaired without publishing a false business-state change.
- Completed transaction cost receipts with all persisted local/base cost-basis and realized-P&L
  components while excluding those calculated outputs from replay inputs, so stale persisted values
  cannot destabilize idempotent input identity. Booked transactions now carry typed optional
  lineage internally while both Kafka mappers continue to omit this derived evidence from the
  established transport contract. Position-history receipts bind that upstream lineage.
- Added one compact cost-basis transition receipt per calculation. It binds the consuming
  transaction identity and lineage, ordered processed-transaction receipts, transition kind, and
  final lot-state snapshot. Each persisted lot then binds that receipt and its own prior durable
  lineage, retaining change sensitivity without transaction-by-lot hashing. AVCO receipts likewise
  bind prior row/checkpoint lineage and the exact transition receipt while preserving bounded,
  set-based database work.
- Replaced trust-by-declaration boundary coverage with a directed source call graph. Exact imported
  symbols and module-qualified calls resolve to exact callables; same-file calls resolve locally;
  ambiguous bare names fail closed; and protocol-style attribute dispatch remains conservative.
  Negative tests prove that unrelated same-named functions, shared-helper siblings, aliased imports,
  and unaliased dotted imports cannot certify a declared boundary.
- Removed the unused `CostLot.total_cost_local` and `CostLot.total_cost_base` compatibility
  properties after repository-wide usage analysis proved that no caller consumed them.

The later cashflow persistence slice adds one nullable JSON column and no topic or runtime-topology
change. Exactly representable inputs, cashflow formulas, serialized Decimal amounts, transaction
identity, and public response shapes remain unchanged.

## Evidence

- Signed commits `5fa97db88`, `c1132d7cf`, `f67c82e38`, `ba34863b3`, and `0a63edafe`.
- 174 warning-strict cashflow, position, event, and arithmetic-context tests passed.
- Simulation request, application-bypass, router, and OpenAPI tests cover float, excess-scale,
  magnitude, non-finite, nonpositive-price, and exact-boundary behavior.
- Repository-native type checking passed across 240 source files.
- OpenAPI quality, API vocabulary parity, financial-numeric persistence, domain-layer, Ruff,
  formatting, and diff-hygiene gates passed.
- Signed commits `0cfbb2c57`, `fb83c0819`, and `8454cbaca` continue the review.
- 87 warning-strict lineage, precision, accrued-income, and position-valuation tests passed,
  including policy-version hash changes, ambient-context independence, half-even normalization,
  component reconciliation, and pre-persistence overflow rejection.
- Repository-native MyPy passed across 240 source files.
- Signed commits `5f5ceac94`, `44bc50938`, `de6785f5a`, and `cd8bb4484` add,
  enforce, coverage-harden, and exact-head review-harden the policy inventory. The final review fix
  requires a real arithmetic or normalization call, including through a local alias; lineage-only
  references cannot satisfy execution-use evidence.
- Signed commits `123471fe8` and `f9ff1d582` address the accepted per-consumer review findings.
  Call-site hardening associates execution and lineage evidence with the enclosing callable so one
  bound function cannot hide an unbound sibling in the same file.
- Signed commit `9535ccf0e` resolves direct `as` imports, module-qualified policy access, and local
  assignments from qualified policies, so an aliased unbound consumer cannot bypass the inventory.
- Eighty-nine focused guard tests passed with 99.21% combined line/branch coverage, including
  repository parity;
  mutation-style shape drift; malformed envelopes and policy entries; stale, unclassified, unused,
  partially bound, and missing-lineage policies; ambiguous/duplicate source declarations; duplicate
  JSON keys; exact callable-gap parity; same-file bound/unbound siblings; imported and qualified
  aliases; CLI success/failure evidence; rejection of lineage-only pseudo-use; discarded-identity
  and overwritten-identity rejection; extracted, chained, overwritten, and parameter-shadowed
  execution aliases; constructor aliases; conditional-only rejection and all-exit acceptance; and
  zero-iteration sync/async loops, loop `else`, normal/exception-group handlers, guarded match
  cases, cross-branch execution/lineage mismatch, unrelated same-named builder rejection, and
  verified direct, local-name, module-alias, and fully qualified lineage propagation; expression
  branches, short-circuit exits, intervening exceptional exits, predicate propagation, and governed
  positional/keyword-only defaults are mutation-proved, along with unreachable callable and branch
  lineage rejection. Signed commit `5694b6996` adds the #845 matrix across all four tracked alias
  classes for aliased `import`, aliased `from ... import`, ordinary dotted import, ordinary
  `from ... import`, and wildcard import, plus valid policy and canonical-builder reinstallation
  after invalidation. PR #846 review then proved that a same-named constant imported from an
  unrelated module could be reinstalled as trusted. The fix derives each policy's importable module
  from its declaration path, resolves absolute and relative imports against the consumer module,
  and reinstalls a policy alias only when those modules match. Ninety-eight warning-strict guard
  tests cover valid declaration imports plus unrelated absolute, relative, and aliased collisions.
- Signed commits `d5972b4d4` and `fef520f84` add the Query Service response contract and generated
  vocabulary truth. Nine focused DTO tests, one live OpenAPI assertion, and 715 warning-strict
  Query Service unit/integration tests passed; OpenAPI quality, vocabulary parity, MyPy across
  240 source files, Ruff, formatting, and diff hygiene passed.
- Signed commits `285005d1e` and `a4707efb1` bind and persist canonical cashflow calculation
  lineage. The final slice passed 158 focused warning-strict tests, migration smoke at single head
  `c130b2c3d503`, MyPy across 240 source files, Ruff, the calculated-output guard, and a rebuilt
  real-PostgreSQL backdated-rebuild proof (`1 passed in 375.02s`).
- PR review fix-forward adds ambient-precision determinism with component fees and booked-versus-
  effective FX transaction identity proof; 88 warning-strict cashflow calculation tests passed.
- Signed commits `f2b88de1b`, `514259f24`, `b10c68022`, and `a30e07c77` close the valuation-family
  callable gaps and persist legacy non-flat calculation lineage. Eighty warning-strict focused
  tests, single-head migration smoke at `c131b2c3d504`, MyPy across 240 source files, Ruff, format,
  calculated-output-policy, domain-layer, and diff guards passed. A rebuilt exact-image PostgreSQL
  persistence test passed (`1 passed in 404.20s`); the preceding stale-image constraint failure was
  classified as invalid diagnostic evidence.
- PR #855 review fix-forward passed 74 warning-strict day-count, accrued-income,
  position-valuation, and migration tests, including opposite ambient rounding modes and downgrade
  operation ordering; calculated-output-policy, migration smoke, MyPy, and focused Ruff gates also
  passed.
- Signed commits `498cb0514`, `443d53b67`, `500bbdfbb`, `b62b8e892`, and `7d1899b53`
  implement the five remaining owner families. Their focused suites passed 21, 113, 83, 57, and
  203 tests respectively, with repository-native Ruff and MyPy validation.
- The closure guard suite passes 105 tests; `make calculated-output-policy-guard` reports eight
  classified policies and `make financial-numeric-persistence-guard` reports 98 Numeric columns
  across 31 tables, 97 bounded and one exact-unbounded, with zero planned gaps.
- Four exact-source PostgreSQL lifecycle proofs pass in 403.47 seconds: FIFO transaction cost,
  lot-state and chained position-history lineage; AVCO source and pool lineage; deterministic
  position-timeseries replay; and owned-lease portfolio-timeseries persistence with its completion
  event. The preceding cached-image run stopped before migrations `c134` through `c138` and failed
  on absent columns; rebuilding the branch-qualified runtime converted all four to green and is
  retained only as invalid stale-runtime diagnostic evidence.
- PR #877 fix-forward passes the warning-strict AVCO/position-materialization tests, MyPy across 241
  source files, focused Ruff/format/diff gates, and exact-source PostgreSQL AVCO row-output-hash and
  bounded-work proofs. Final transaction processing/buy contract and protected CI evidence are
  recorded on PR #877 and issue #829 at the exact signed head.
- Final PR review found two remaining evidence-boundary gaps: the incremental AVCO path did not bind
  the triggering application transition into its aggregate receipt, and position-timeseries input
  omitted the already-persisted valuation and cashflow receipts. The application now supplies one
  required typed transition-evidence value through the AVCO port and repository, while current,
  prior, and future snapshot reads outer-join typed valuation lineage and both cashflow paths reuse
  their selected lineage without extra queries. Source-revision-only tests prove lineage hashes
  change while scalar financial outputs remain identical; legacy rows with absent lineage remain
  supported. The combined warning-strict review suite passes 70 tests.
- A subsequent final review cycle closed the same pattern across downstream boundaries. Full AVCO
  rebuild plans now carry ordered canonical-history and processed-transaction replay lineage; rebuilt
  source receipts bind it, and the replacement checkpoint deterministically binds replay evidence
  plus final checkpoint output without self-chaining overwritten state. Reconciliation compares that
  receipt under the existing per-key lock, refreshes evidence-only drift, and remains idempotently
  current on a second identical run. Position materialization distinguishes numeric change from evidence refresh so lineage-
  only changes continue dependent replay and stage portfolio aggregation without inflating numeric
  change reporting. Portfolio contributions now carry the selected typed FX fact, including currency
  pair, effective date, persisted row identity, and aware source revision; equal scalar rates from
  different facts therefore retain different receipts. These changes reuse existing rows and query
  shapes except for the bounded AVCO rebuild's prior-checkpoint evidence read; they add no hot-path
  N+1 behavior. The combined focused review suites pass 91 tests.
- The final late-review pass found that reconciliation compared the canonical full-replay receipt
  byte-for-byte with healthy receipts emitted by ordinary incremental transition and checkpoint
  writers. Because algorithm identity is part of the calculation hash, exact economics could be
  falsely reported as drift. Reconciliation now requires exact receipt equality for a prior rebuild,
  but recognizes only the two repository-owned incremental algorithm identities when their version,
  precision, numeric policy, complete source aggregates, and pool aggregates match replay truth.
  Unknown writers and changed rebuild evidence still fail closed. The assessment model also records
  evidence-only drift without pretending that financial amounts differ. Twenty-four focused tests,
  Ruff, and MyPy pass, including both healthy incremental writers, changed replay evidence, and an
  unknown-writer negative case.
- The last review pass extended that same completeness rule to the ordinary backdated-processing
  path and opening-lot rows. A non-incremental AVCO checkpoint now binds the existing typed
  transition receipt containing the triggering transaction and all processed calculation receipts;
  reconciliation recognizes that repository-owned writer only when complete economics and governed
  calculation semantics agree. Opening-lot output lineage now includes the persisted accrued-
  interest-paid amount. Tests prove identical ending pool economics retain distinct inputs for
  different processed evidence, and a changed accrued-interest output changes the lot output hash.
  The combined warning-strict focused suite passes 43 tests, with Ruff and MyPy green.

## Compatibility and remaining work

The simulation contract intentionally rejects values that could previously be changed or rejected
only after acceptance. Gateway #511 is exact-main complete. Accrued-income and position-valuation
lineage hashes intentionally change because numeric policy is now calculation identity. Query
Service calculation-lineage responses now expose an additive optional policy object; calculations
that do not execute a governed output policy remain valid with `numeric_output_policy=null`.
The declaration inventory is complete and enforced. All eight calculated-output families are
lineage-bound at their accountable output boundary. Additive nullable persistence keeps legacy rows
valid and explicitly unknown rather than inferring current-policy evidence. Formulas, normalized
values, public response shapes, topic contracts, and runtime topology are unchanged.

## Documentation decision

Repository context, the machine-readable policy standard, and this existing review record carry the
implementation detail without adding a duplicate document. No route, public response, operator
command, topic, runtime topology, or wiki-owned workflow changed, so no OpenAPI or wiki source
change is required.
