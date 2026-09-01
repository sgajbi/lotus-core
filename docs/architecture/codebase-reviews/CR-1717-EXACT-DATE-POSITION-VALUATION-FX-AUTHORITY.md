# CR-1717: Exact-Date Position-Valuation FX Authority

## Finding

The position-valuation repository selected the latest direct FX observation on or before the
requested valuation date. Both valuation paths accepted that row and classified the resulting
snapshot as `VALUED_CURRENT`. A missing current-day observation could therefore silently become a
plausible current market value backed by older FX evidence.

## Financial invariant

A successful cross-currency position valuation for a business date must use a direct FX
observation owned by that exact date. An older observation is not current valuation authority and
must fail closed before a supported receipt or market value is persisted.

Same-currency conversion remains an identity operation and must not require an FX observation.

## Implementation

- The valuation repository exposes `get_exact_fx_rate(...)` and its SQL requires
  `rate_date == valuation_date` after canonical currency normalization.
- The authoritative and legacy position-valuation paths share the exact-date resolver.
- The application boundary rejects a non-null adapter result when its source date does not equal
  the event valuation date. This protects the invariant even when a test double or future adapter
  violates the repository contract.
- Missing and prior-date FX follow the established failed-valuation recovery path: the failed
  candidate has no market value, any successful valuation receipt is removed, the job records the
  exact-date failure, and the existing failure event remains available to operations.

The source-evidence and receipt schema introduced under CR-1715 already records the selected FX
date and rate for successful valuation. This slice makes that recorded evidence exact rather than
adding a competing provenance contract.

## Scope

This is one financial invariant in the position-valuation ownership boundary. It does not change
APIs, OpenAPI, schemas, migrations, event shapes, formulas, dependencies, images, datastores, or
runtime topology.

Latest-on-or-before reads used by historical timeseries and cost-basis workflows have different
temporal contracts and were not changed. Reconciliation classification and remediation of already
persisted stale valuation rows remain follow-on acceptance work under #997.

## Evidence

- Warning-strict processor and repository tests cover exact-date success, missing FX, prior-date
  adapter output, same-currency identity, receipt removal, failed value persistence, and retained
  recovery publication.
- A real PostgreSQL repository test proves a prior-day EUR/USD row is not selected for the
  valuation date and that adding the exact-date row makes only that row authoritative.
- The same-pattern scan found both production position-valuation paths use the shared exact-date
  resolver; no remaining caller uses the former ambiguous repository method.
- PR #1082 merged by rebase with four signed commits after all protected checks and exact-head
  review passed. Main Releasability run `33532530148` passed on exact main
  `c4fa01ca542d7aacff76e8c7ab4bec558e546ab2` with 25 successful jobs, zero failures, and two
  policy skips.
