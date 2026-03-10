# CR-076 E2E Failure-Scenario Output Noise Review

## Scope
Reduce low-signal console chatter in `tests/e2e/test_failure_scenarios.py` while preserving explicit operator visibility when detailed debugging is needed.

## Findings
- `tests/e2e/test_failure_scenarios.py` printed a long sequence of progress markers unconditionally:
  - PostgreSQL readiness
  - per-service health confirmation
  - DLQ verification
  - recovery barrier status
- Those prints were helpful during incident debugging, but they made successful runs noisy and inconsistent with the quieter harness policy introduced in CR-075.

## Changes
1. Routed progress output in `tests/e2e/test_failure_scenarios.py` through:
   - `tests.test_support.output_control.emit_test_output`
2. Kept the highest-value recovery-step messages visible by default.
3. Moved repetitive readiness and DLQ-confirmation chatter behind verbose mode.
4. Left runtime behavior unchanged; this slice is output-policy only.

## Validation
- `python -m pytest tests/e2e/test_failure_scenarios.py -q`
- `python -m ruff check tests/e2e/test_failure_scenarios.py tests/test_support/output_control.py tests/conftest.py`

## Residual Risk
- If another high-noise E2E module is added later, it should use the same shared output helper instead of direct `print(...)`.
