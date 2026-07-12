# CR-075 Test Harness Output Control Review

## Scope
Reduce low-signal test harness chatter in `tests/conftest.py` without losing the ability to inspect detailed lifecycle output when debugging Docker-backed runs.

## Findings
- `tests/conftest.py` printed many lifecycle messages unconditionally:
  - runtime banner
  - migration wait
  - Kafka readiness
  - per-service health confirmations
  - DB cleanup notices
  - teardown notices
- This was useful during deep E2E debugging, but it made routine integration/E2E output noisy and harder to scan.
- The harness did not have an explicit output policy beyond always printing everything.

## Changes
1. Added shared test-output helpers:
   - `tests/test_support/output_control.py`
2. Introduced explicit verbose-mode control via:
   - `LOTUS_TESTS_VERBOSE`
3. Routed `tests/conftest.py` lifecycle output through the helper so:
   - important session milestones still print
   - high-churn details such as per-service health confirmations and cleanup chatter become verbose-only
4. Added unit coverage for the helper behavior.

## Validation
- `python -m pytest tests/unit/test_support/test_output_control.py -q`
- `python -m pytest tests/unit/test_support/test_runtime_env.py -q`
- `python -m pytest tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py -q`
- `python -m pytest tests/e2e/test_ingestion_service_api.py -q`

## Residual Risk
- This improves readability, not runtime semantics.
- If future debugging needs more detail, operators can enable:
  - `LOTUS_TESTS_VERBOSE=1`
