# CR-1729 — Integration Full abnormal-exit evidence

Status: In Review

Date: 2026-09-21

Owner: lotus-core
Issue: #1129

## Review unit and classification

Pattern: heavy-gate process diagnostics and test-result survival. This is a testing/CI and
observability gap, not evidence by itself of a financial-calculation or architectural defect.

On exact-main run `35518463975` and branch diagnostic `35521390722`, Integration Full stopped
during `test_thousand_member_release_drains_with_bounded_progress_validation` after the
120-second stack diagnostic, and `make` reported exit 245. An unchanged-SHA retry
`35514199074` passed the same test despite also emitting the 120-second diagnostic. The prior
runner returned the pytest child status directly. JUnit was written only at normal session end;
the failed jobs retained neither that file nor the Compose teardown artifact. Exit 245 alone
does not establish the child signal or root cause.

## Bounded hardening

- Keep the 1,000-member assertion, SQL-work ceiling, timeout diagnostic, and required gate.
- Append each started node and completed pytest phase to a run-specific JSONL journal before
  session teardown. A native exit can leave an unmatched start event, not a false pass.
- Have the parent manifest runner retain the signed child return code, signal name when negative,
  elapsed time, and Linux peak child RSS in a distinct JSON artifact. Return the original child
  code, including failure, rather than treating artifact creation as success.
- Upload journal and parent record with `if: always()` alongside JUnit and Compose logs.
- Keep the 1,000-member worker test on a governed queue-pooled async PostgreSQL engine. The
  shared integration fixture deliberately uses `NullPool`; borrowing it for every worker unit of
  work forced one physical PostgreSQL connection per unit of work, unlike the pooled
  production worker. Count actual physical connections while retaining the 1,000-member,
  readiness-authority and SQL-statement ceilings.
- Keep the source/test change in one signed commit because the slice touches a release workflow.

The change is test/CI evidence only. It changes no application/domain/persistence ownership, API,
financial formula, schema, event contract, runtime topology, or lease/rollback fence. The closest
same-pattern scan found other suite runners sharing `run_suite`, but this loss of end-of-session
JUnit is specific to the hosted `integration-all` job; other suites keep their existing behavior.

## Acceptance and limits

Focused tests must fail on the old runner and absent upload paths, then pass after correction.
An actual abruptly terminated miniature pytest child must leave a started-node journal without a
completed call phase. The parent must distinguish `0`, ordinary nonzero, and negative signal exit
without masking them. Workflow/documentation checks and final-head review/CI must pass, then an
exact-main Integration Full run must retain the new artifacts on either outcome.

This instrumentation does not claim to fix the underlying intermittent exit. #1129 remains open
until repeated evidence distinguishes native failure, database slowness, resource exhaustion,
diagnostic-timer interaction, or fixture contention and the 1,000-member behavior is stable.
Do not substitute a 100,000-transaction bank-day run for this focused investigation; #714/#794
own that separate capacity question, and the owner has withdrawn further 100k tests.

## Evidence checkpoint

- Initial red: 4 focused tests failed for missing runner fields and workflow upload paths;
  plugin import failed at collection before implementation.
- Corrected focused pack: 8 passed in 1.46 seconds, including a real pytest child
  `os._exit(93)` that left an unmatched journal start and a real abrupt runner child whose
  signed exit survived in the parent JSON; targeted Ruff check/format passed.
- Relevant manifest/workflow/journal unit modules: 51 passed, including both abrupt-child
  controls and preservation of the child failure when the parent diagnostic write fails. Full
  repo lint, typecheck (329 files), documentation evidence, and
  workflow-governance gate (538 passed at 94% branch-aware coverage) passed locally.
- The source maintainability ratchet passes for 1,168 tracked modules under the governed Python
  3.11 environment. Bare `make` on this workstation selects Python 3.13 and reports a 0.02 index
  drift for an untouched analytics module; no baseline was changed for that interpreter variance.
- Cheap real-PostgreSQL regression: 12 sequential sessions with the old `NullPool` worker setup
  opened 12 physical connections and failed the new one-connection bound; the governed queue-pool
  version reused one connection and passed. The unchanged 1,000-member business and SQL-work
  assertions passed three times locally with the pooled worker, in 109.14, 114.49 and 112.77
  seconds. An earlier pooled attempt returned `IDLE`, so the test now records the persisted
  release status if that recurs; neither connection churn nor the `hmac._init_hmac` stack snapshot
  alone proves the cause of hosted exit 245.
- Final-head CI, exact-main artifact, and root-cause classification: pending.
- Wiki source updated in `wiki/Validation-and-CI.md`; publish only after merge and verify parity.
- No central skill/routing/context change is warranted: this is an app-local evidence gap under
  existing CI and demo-certification controls.
