# CR-1633: Effective Portfolio Party Roles

## Objective

Replace ambiguous portfolio-master adviser interpretation with source-owned, effective-dated
private-banking role assignments while keeping existing PM-book consumers compatible during a
controlled migration.

## Finding

GitHub issue #513 identified that `Portfolio.advisor_id` could represent a relationship manager,
investment adviser, portfolio manager, assistant RM, service officer, external asset manager, or
temporary delegate. The field carried no capacity, responsibility scope, effective interval,
source authority, observation time, or data-quality disposition. The existing
`PortfolioManagerBookMembership:v1` reader then interpreted every matching value as portfolio-
manager membership.

No authoritative Party aggregate currently exists in Core. Creating one here would duplicate the
separately governed #518 party/client/beneficial-owner scope, so this slice keeps `party_id` as a
required source-owned identifier and enforces only portfolio ownership through a foreign key.

## Change

- Added governed role, responsibility-scope, and quality-status vocabularies that distinguish
  relationship coverage, investment advice, portfolio management, and client service.
- Added `portfolio_party_role_assignments` with effective dates, source identity, observation time,
  version, quality disposition, database vocabulary/interval/version constraints, replay
  idempotency, and accepted-current/history indexes.
- Added a validated, idempotent reference-data ingestion endpoint and an additive
  `PortfolioPartyRoleAssignment:v1` Query Control Plane source product.
- The as-of reader ranks the latest version of each source record before applying effective-window
  and quality filters. A later quarantine, rejection, expiry, or correction cannot make an older
  accepted version silently reappear.
- `PortfolioManagerBookMembership:v1` now resolves only `portfolio_manager` and
  `discretionary_portfolio_manager` assignments in `portfolio_management` scope. Its legacy
  `advisor_id` projection remains available only for portfolios with no role-assignment history.
- Fixed the generated route inventory to use each source product's approved consumers instead of
  applying a generic route-family list that contradicted catalog ownership.
- Fixed PR review trust classification for the explicit `include_non_accepted` diagnostic path.
  Accepted-only results are `COMPLETE/READY`; empty results remain `MISSING/INCOMPLETE`; any
  returned pending-review, quarantined, or rejected assignment is now `PARTIAL/INCOMPLETE` with an
  explicit `PARTY_ROLE_ASSIGNMENTS_NON_ACCEPTED` reason. Diagnostic rows remain visible without
  being misrepresented as usable relationship authority.
- Fixed a second PR review identity gap: snapshot, content, source-batch, and source-digest identity
  now bind the full returned assignment rows, request scope, aggregate quality/supportability,
  latest evidence timestamp, and lineage. A same-version correction to an effective interval,
  role/scope, party, or quality disposition therefore changes the receipt identity instead of
  retaining the request-and-version fingerprint.
- Applied the same evidence-identity rule to `PortfolioManagerBookMembership:v1`. Its receipt now
  binds the normalized request scope, complete returned member evidence, supportability, latest
  evidence timestamp, and legacy-versus-authoritative lineage. Replacing a legacy adviser
  projection with a party-role assignment, or correcting its source-record evidence, changes the
  snapshot, content, source-batch, and source-digest identities even when portfolio IDs are
  unchanged.
- A downstream canonical-proof review found Gateway's implemented advisor-book facade absent from
  the producer's approved-consumer tuple. The live source catalog and repo-native RFC-0084
  declaration now approve `lotus-gateway` alongside `lotus-manage`; a direct regression protects
  both declaration parity and `products_for_consumer("lotus-gateway")` discovery.
- A final contract/runtime review found that accepted PM-book results inherited the shared
  `false` / `UNAVAILABLE` trust default because this product uses the source quality term
  `ACCEPTED`. The response boundary now derives currentness from both returned membership and a
  linked evidence timestamp, emits `true` / `CURRENT` only when both exist, keeps empty or
  timestamp-free evidence fail-closed, and binds the resulting trust fields into receipt identity.
- Cross-repository pre-merge review then found that the canonical contract promised an
  authoritative `PM_SG_001` book assignment while Core's executable seed still populated only the
  compatibility `advisor_id`. The canonical bundle now derives the effective-dated assignment
  from the platform contract, posts it through the real party-role ingestion endpoint, removes it
  during bounded reseed cleanup, and refuses runtime verification until Gateway returns the
  portfolio with `governed_role_assignment` lineage and current source evidence. A standalone
  executable validator proves the bundle and ingestion request use the same runtime builders.

## Compatibility And Same-Pattern Review

The new ingestion and query contracts are additive. The PM-book route and product version remain
`v1`; member responses add `membership_source` and optional governed `role_type`, while lineage now
states whether membership came from role assignments or the bounded legacy projection.
`Portfolio.advisor_id`, its ingestion/query DTO fields, and its supporting index remain explicitly
compatibility-only until Gateway #500 and Workbench #450 complete downstream cutover. Transaction
RFC `advisor_id` metadata was reviewed and left unchanged because it is source transaction context,
not portfolio relationship ownership. Broader Party modeling remains #518 and vocabulary linting
remains #521.

## Validation

- governed role vocabulary: 4 tests passed;
- ORM and executable migration contract: 25 tests passed;
- ingestion DTO, registry, persistence, router, and OpenAPI: 80 tests passed;
- assignment application/SQL/catalog/security/OpenAPI: 83 tests passed;
- PM-book precedence, compatibility, migration-index, router, and source-product cohort: 121 tests
  passed;
- targeted Ruff and MyPy passed for every changed production module;
- Alembic reports the single head `c115b2c3d4f4`; migration contract validation passed.
- route-catalog generator tests and strict MyPy passed; regenerated consumers now match the
  source-product catalog.
- isolated PostgreSQL 16 proof applied the full migration chain through `c115b2c3d4f4`, then passed
  the role-resolution integration test (1 test) covering latest-version quarantine precedence,
  the migrated-portfolio legacy fence, authoritative accepted-role membership, and idempotent
  version upsert;
- migration reversibility was proved by downgrading `c115b2c3d4f4 -> c114b2c3d4f3`, confirming the
  assignment table was absent, upgrading back to the single head, and confirming it was present.
- the complete non-database #513 regression cohort passed with 206 tests after final formatting and
  gateway-policy reconciliation;
- full repository Ruff lint/format and MyPy across 235 source files passed;
- architecture, application-layer/port/dependency-inversion, ingestion-framework,
  infrastructure-adapter, source/domain-product, route-family, OpenAPI, API-vocabulary,
  documentation, and wiki-source gates passed;
- the same-pattern endpoint scan in the lint lane found the new write route absent from the
  gateway-owned global ingestion rate-limit contract; the policy was corrected and its four guard
  tests passed.
- focused application regressions cover accepted-only, empty, and mixed accepted plus each of
  pending-review, quarantined, and rejected source dispositions.
- the final exact-worktree combined coverage gate passed 5,116 unit, 12 unit-database, 55
  critical-database, 138 integration-lite, and 284 operations-contract tests with zero warnings;
  aggregate query coverage was 97.693%, measured changed-source coverage was 97.401% total and
  91.261% branch, and changed critical sources reached 97.55% line and 92.38% branch coverage;
- the final full lint chain passed across 2,058 files and strict MyPy passed across 237 source
  files after the PR review correction.
- two PM-book evidence-transition regressions and the shared-consumer cohort passed in a focused
  `79`-test run; scoped Ruff and strict MyPy across `237` sources passed at signed fix-forward
  commit `a86d200c4`.
- the Gateway-consumer correction passed 25 focused source-product/declaration/audit tests plus the
  repo-native domain-product validator, source-data-product contract guard, RFC-0083 closure guard,
  and diff hygiene.
- populated, empty, timestamp-free, authoritative-role, and evidence-transition PM-book trust
  regressions protect the product-specific currentness policy without changing its
  `ACCEPTED`/`MISSING` data-quality vocabulary.
- the final trust fix passed 39 warning-strict metadata/application tests and a 120-test PM-book,
  router, and shared source-product cohort; strict MyPy passed all 237 source files, and the full
  architecture, domain-product, source-product, RFC-0083, route-catalog, documentation, and wiki
  guard set passed.
- canonical seed proof passed 63 focused tests; the executable advisor-book validator reported one
  `PM_SG_001` assignment at `/ingest/portfolio-party-role-assignments` with governed source record
  `pb_sg_global_bal_001_pm_sg_001_portfolio_manager_v1`.

Local acceptance is complete. PR CI, merge, exact-main validation, wiki publication, and verified
issue closure remain required before #513 is done.

## Documentation Decision

Repository context, source-product and route catalogs, schema catalog, the historical PM-book
ownership review, the downstream endpoint audit, this ledger, and the existing Mesh Data Products
wiki source change because public ownership truth changed. No new standalone methodology or skill
was added: existing effective-date, source-product, delivery, review-ledger, and issue-resolution
governance already covers the reusable procedure without duplicating content.

The PR review correction does not require an additional wiki edit: the existing wiki describes the
source-owned quality disposition, while exact aggregate quality/supportability precedence belongs
in the API contract, executable tests, and this review record.

The receipt-identity correction likewise needs no additional wiki page. The existing Mesh Data
Products page owns the audience-facing source-product description; exact hash inputs and correction
behavior are implementation, executable-test, and review-ledger truth.

The consumer-approval correction updates that existing wiki row rather than adding a new page.
Gateway's repo-native consumer declaration and federated platform discovery artifacts remain
downstream merge dependencies; catalog approval alone is not end-to-end certification.

The trust-metadata correction updates the same Mesh Data Products row. No standalone trust page is
needed: executable response tests and this review record own the precise currentness algorithm,
while the wiki states the customer- and operator-facing fail-closed behavior.

The canonical seed correction also updates that row rather than adding another page. The runtime
builder, executable validator, and tests own exact payload mechanics; the wiki records that
canonical proof now requires authoritative assignment lineage rather than compatibility fallback.

PM-book membership is a source data product rather than a financial calculation, so it binds
request/input and returned-evidence identity but does not invent a calculation-lineage envelope.
Financial outputs continue to require explicit input, calculation/policy, and output lineage under
the existing calculation-lineage contract and issue #788.
