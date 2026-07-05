# CR-1392 Synthetic Test-Data Governance

## Objective

Fix GitHub issue #610 by making synthetic fixture safety and reusable private-banking fixture
coverage explicit, testable, and enforced through a repo-native command.

## Finding

Core had representative seeds, API examples, redaction tests, and generated-artifact tracking, but
no single governed test-data standard proving that committed fixtures, examples, seed surfaces, and
generated proof artifacts avoid client data, credentials, account-like values, or real-looking
personal names. The canonical front-office seed contract docs also carried a human-looking client
display name.

## Actions

- Added `docs/standards/synthetic-test-data-governance.v1.json` with naming, leakage, realism, and
  catalog rules.
- Added `tests/fixtures/private-banking-portfolio-fixture.v1.json` covering client, account,
  portfolio, custody, instrument, transaction, cash, FX, benchmark, and reporting-currency
  relationships.
- Added `scripts/synthetic_fixture_leakage_guard.py` and unit tests for credential, database URL,
  personal data, account-number, uncataloged CIF-style ID, and relationship-coverage failures.
- Wired `make synthetic-fixture-leakage-guard` into `make lint`.
- Replaced the human-looking front-office seed display name in Core docs with a synthetic label.

## Compatibility

No runtime behavior, API route, DTO, OpenAPI schema, database schema, Kafka topic, event payload, or
deployment topology changed. Existing canonical seed identifiers remain compatible and are now
cataloged as synthetic authored identifiers.

## Validation

Run before commit:

- `python -m pytest tests/unit/scripts/test_synthetic_fixture_leakage_guard.py -q`
- `python scripts/synthetic_fixture_leakage_guard.py`
- `make synthetic-fixture-leakage-guard`
- scoped Ruff lint and format over the new guard/tests
- `make risk-based-test-coverage-matrix-guard`
- `make quality-wiki-docs-gate`
- `git diff --check`

## Guidance Decision

Repo-local context and testing strategy changed because this is a durable Core fixture/evidence
rule. No platform skill change is required for this slice: the existing issue loop and backend
delivery skills already require promoting repeatable patterns into validators or context.
