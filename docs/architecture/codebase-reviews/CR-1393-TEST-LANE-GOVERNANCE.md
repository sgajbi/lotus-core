# CR-1393 Test Lane Governance

## Objective

Fix GitHub issue #611 by making integration/E2E lane placement, deterministic test expectations,
marker taxonomy, and flaky-test quarantine policy explicit and enforced by a repo-native guard.

## Finding

Core already had strict pytest markers, runtime-mode detection, isolated test runtime environment
profiles, and a Make-backed test manifest. The missing governance was a durable contract that maps
markers to CI lanes, proves live-worker/Docker tests cannot drift into the unit lane, and blocks
indefinite flaky-test quarantine.

## Actions

- Added `docs/standards/test-lane-governance.v1.json` with marker taxonomy, deterministic
  clock/ID/business-date guidance, bounded polling rules, parallel isolation policy, CI lane
  mapping, quarantine policy, and flake-tracking report location.
- Added `scripts/test_lane_governance_guard.py` and unit tests for current repo truth, generated
  flake report, missing marker, unit-lane runtime drift, and expired quarantine failure.
- Added `unit`, `domain`, `performance`, `resilience`, `certification`, and `flaky_quarantine`
  pytest marker declarations while preserving strict marker enforcement.
- Strengthened the unit manifest marker exclusion to block `integration_db`, `db_direct`,
  `live_worker`, and `e2e` tests from accidental fast/unit execution.
- Wired `make test-lane-governance-guard` into `make lint`.

## Compatibility

No runtime behavior, API route, DTO/OpenAPI schema, database schema, Kafka topic, event payload, or
deployment topology changed. Unit suite selection is intentionally stricter for runtime markers.

## Validation

Run before commit:

- `python -m pytest tests/unit/scripts/test_test_lane_governance_guard.py -q`
- `python scripts/test_lane_governance_guard.py`
- `make test-lane-governance-guard`
- scoped Ruff lint and format over the new guard/tests
- `python scripts/test_manifest.py --suite unit --collect-only --quiet`
- `python scripts/test_manifest.py --suite integration-lite --collect-only --quiet`
- `make quality-wiki-docs-gate`
- `make lint`
- `git diff --check`

## Guidance Decision

Repo-local context, testing strategy, and wiki source changed because test lane governance is a
durable Core contributor rule. No platform skill change is required for this slice; the existing
backend delivery and issue loop skills already require converting repeated quality failures into
repo-native guards and context.
