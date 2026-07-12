# CR-007 Failure-Recovery Semantics Review

## Scope

Review the semantics, observability model, and testability of the failure-recovery gate:

- `scripts/failure_recovery_gate.py`
- ingestion health surfaces exposed via `event_replay_service`
- related backlog / error-budget instrumentation

## Findings

### 1. The current gate is operationally useful but semantically ambiguous

The gate currently passes if:

- backlog grows during interruption
- backlog age after recovery is below threshold
- DLQ pressure after recovery is below threshold
- replay pressure after recovery is below threshold

It does **not** require `drain_seconds_to_baseline` to succeed in all cases.

Current behavior:

- if drain completes and is too slow, fail
- if drain times out but backlog-age is still below the configured ceiling, pass

This is internally coherent, but it is not obvious from the report headline.

Operational implication:

- a run can be marked `Overall passed: True`
- while `drain_seconds_to_baseline = timeout`

That does not mean the system is broken. It means the gate is currently testing
“bounded recovery under pressure” rather than “strict full drain to baseline”.

### 2. The current report does not explicitly name the recovery mode

The JSON and Markdown artifacts show the raw fields, but the result does not classify
the recovery shape.

Missing concept:

- `strictly_drained`
- `bounded_but_not_fully_drained`
- `unhealthy_recovery`

Without that classification, operators and engineers can misread the same report.

### 3. The instrumentation is good enough to extend, not replace

Useful signals already exist:

- `backlog_jobs`
- `backlog_age_seconds`
- `dlq_pressure_ratio`
- `replay_backlog_pressure_ratio`

This means the next step is not a new gate from scratch.
The next step is to make the result classification explicit and better tested.

### 4. The real missing test layer is semantic classification

There is strong lower-level coverage for ingestion health calculations.
What is missing is direct unit coverage for the gate's own decision table:

- fast full drain => pass
- slow but bounded recovery => pass, but explicitly classified
- drain timeout plus elevated backlog age => fail
- elevated DLQ pressure => fail
- weak backlog growth during interruption => fail

This is a testability gap in the gate script itself, not primarily in the ingestion service.

## Recommendation

Keep the current bounded-recovery policy for now, but make it explicit:

1. add a recovery classification field to the gate result:
   - `FULLY_DRAINED`
   - `BOUNDED_RECOVERY`
   - `FAILED_RECOVERY`
2. add direct unit tests for the classification/threshold matrix
3. update the Markdown report so a timeout-to-baseline is never visually mistaken for a clean full drain

Do **not** tighten the thresholds blindly before classification exists.
That would change policy before improving clarity.

## Implementation update

Implemented:

- explicit recovery classification in `scripts/failure_recovery_gate.py`
  - `FULLY_DRAINED`
  - `BOUNDED_RECOVERY`
  - `FAILED_RECOVERY`
- direct unit tests for the gate decision matrix in:
  - `tests/unit/scripts/test_failure_recovery_gate.py`

Result:

- timeout-to-baseline is no longer semantically ambiguous in the gate output
- reports can distinguish bounded but acceptable recovery from a fully drained recovery

## Sign-off state

Current state: `Hardened`

Reason:

- the ambiguity has been resolved in implementation
- lower-level tests now exist for the decision table
- future work, if any, is policy tuning rather than missing control semantics
