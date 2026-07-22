# CR-129 Quiescence Active-Row Activity Review

## Finding

`wait_for_pipeline_quiescence(...)` already distinguished blocking from non-blocking
tables at the snapshot-count level, but `read_pipeline_last_activity_at(...)` still
looked at the maximum timestamp across the whole blocking tables.

That was wrong for the quiet-window contract:

- the snapshot could already be all zeros
- but historical completed rows in blocking tables could still have recent
  `updated_at` values
- the quiet window would stay open even though there was no live blocking work

This showed up as suite-level E2E cleanup timeouts with an all-zero snapshot.

## Change

Changed `read_pipeline_last_activity_at(...)` to apply the same blocking predicates
used by the snapshot itself when computing last activity time.

A July 2026 exact-main recurrence exposed the complementary zero-row case. When all
blocking rows became terminal, the active-only timestamp query correctly returned
`None`, but `wait_for_pipeline_quiescence(...)` incorrectly treated that absence as
permission to skip the configured quiet interval. The next module then deadlocked a
global `TRUNCATE` against an in-flight valuation-job terminal update. The wait loop now
measures the quiet interval from the first all-zero snapshot when no active timestamp
exists. It retains the active-only query, so unrelated completed history cannot extend
the fence indefinitely.

## Why It Matters

The quiet window should represent the last time *live blocking activity* changed,
not the last time any row in a historically active table changed.

Without this fix, quiescence becomes sensitive to unrelated completed history and
creates false cleanup failures between E2E modules.

Conversely, an all-zero snapshot is a state observation, not proof that the worker
which produced the terminal transition has left its database transaction. The bounded
zero-state timer makes the existing quiet interval effective without reopening the
historical-row defect.

## Evidence

- `tests/test_support/pipeline_quiescence.py`
- `tests/unit/test_support/test_pipeline_quiescence.py`
- exact-main run `29955740903`, job `89050505680`
