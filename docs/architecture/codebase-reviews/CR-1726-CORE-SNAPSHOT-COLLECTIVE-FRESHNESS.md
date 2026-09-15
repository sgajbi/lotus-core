# CR-1726: Core Snapshot Collective Freshness

## Scope And Finding

User-assigned bounded canonical readiness correction under #714. This is not its capacity,
restart, rollout, or downstream acceptance closure. Preserve the consolidated runtime and c168
aggregation/rollback fences.

The supported canonical seed completed persistence, current position state, valuation and exact
financial reconciliation at mixed per-security last-mutation epochs. QCP nevertheless returned
`PARTIAL` quality because freshness required uniform row epochs. The shared collective scope and
the QCP reconciliation read already correctly targeted the maximum valid epoch; freshness used a
contradictory second resolver.

Actual production QCP route/PostgreSQL reproduction at signed `03e2cc18dcee15da268b96fe619d58591fc65834`
returned HTTP 200, reconciliation `COMPLETE`, current source evidence and valuation `READY`, but
null freshness epoch for valid 0/1 sources. The unchanged implementation failed both same-day and
carry-forward expectations. Eight adverse control/source cases retained their negative posture.
[Pre-edit evidence](https://github.com/sgajbi/lotus-core/issues/714#issuecomment-5688602672).

## Correction And Ownership

The QCP application passes its existing `HoldingsReconciliationScopes` to freshness metadata;
the obsolete uniform-row resolver is removed. Framework-independent scope validation remains
shared domain policy. HTTP admission, source-reader ports/SQL, exact durable controls, valuation,
snapshot timestamps and financial arithmetic are unchanged. No new tenant/grant authority or
runtime service boundary is introduced.

Missing/inconsistent collective targets, any unscoped source row and an empty baseline keep the
freshness epoch null. A resolved target alone never establishes completed reconciliation or
current valuation. Reprocessing state remains valuation-unavailable and non-current even if its
financial facts and completed controls are intact.

## Acceptance And Same-Pattern Proof

- Production QCP app, registered route, real PostgreSQL source adapter and durable controls.
- Matched 0/1 source/state epochs with one or multiple financial days and a coherent daily
  valued snapshot date; stable content/snapshot/request/lineage identity on repeated reads.
- Independent quantities 1/2, prices 10/20, values 10/40, total 50 and weights 0.2/0.8.
- Missing, wrong-epoch, pending, failed and stale controls; source/state epoch mismatch;
  reprocessing state and missing valuation. No incomplete evidence is promoted to current.
- Pure guards for missing business date, negative/boolean epochs, empty filtered baseline and
  missing/conflicting collective targets. Shared scope, control, metadata and provenance callers
  were inspected; no second uniform-epoch resolver remains.
- The new PostgreSQL module has `db_direct`/`lifecycle` markers and an explicit bounded coverage
  manifest entry. Both actual premerge PostgreSQL selections execute it.

## Validation And Closure Boundary

Initial local production-route PostgreSQL pack: 10 passed in 71.28s, normal isolated teardown.
Focused metadata/service/manifest pack: 81 passed. These are developer `test_execution` on dirty
base `ffd81e47dcfb96e9a9c3edbca333cc12664fd5cf`, not final-head/mainline or consumer certification.
Final-head lint/typecheck/contracts, required review/CI, exact-main including Integration Full,
authored wiki publication/parity, and qualified isolated Core seed proof remain required.
Workbench/Idea retain independent canonical and durable consumer acceptance after reconstruction.

## Compatibility And Documentation Decisions

`PortfolioStateSnapshot:v1`, its response shape and calculation version remain unchanged: this
restores the existing collective policy documented by CR-1641, not a new financial methodology.
Corrected freshness/trust values intentionally change their bound content and lineage identities;
old partial receipts are not relabeled current. DTO description, authored Query Control Plane
wiki and repository practice are updated. README/operator commands, schema/migrations, events,
dependencies/locks, source-cut/UTC policy, central Platform context/skills and service topology are
explicit no-change. Keep #714 open for its broader production acceptance.
