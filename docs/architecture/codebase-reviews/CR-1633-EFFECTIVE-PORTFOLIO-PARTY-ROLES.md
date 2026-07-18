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

Broad repository-native gates, PR CI, merge, exact-main validation, wiki publication, and verified
issue closure remain required before #513 is done.

## Documentation Decision

Repository context, source-product and route catalogs, schema catalog, the historical PM-book
ownership review, the downstream endpoint audit, this ledger, and the existing Mesh Data Products
wiki source change because public ownership truth changed. No new standalone methodology or skill
was added: existing effective-date, source-product, delivery, review-ledger, and issue-resolution
governance already covers the reusable procedure without duplicating content.
