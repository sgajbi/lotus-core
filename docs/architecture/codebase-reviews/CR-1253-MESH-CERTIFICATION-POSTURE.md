# CR-1253: Mesh Certification Posture

Date: 2026-07-01

## Objective

Fix GitHub issue #694 by clarifying the evidence boundary between active Core source-product
declarations, implementation proof, live validator proof, repo-owned trust telemetry coverage, and
platform mesh certification.

## Expected Improvement

The wiki previously used broad certification language that could be read as mesh certification for
all active Core source products, even though repo-owned trust telemetry currently covers only:

- `PortfolioStateSnapshot:v1`
- `DpmSourceReadiness:v1`

The updated wiki separates:

1. active declaration,
2. implemented / CI-backed proof,
3. live validator proof,
4. repo-owned trust telemetry coverage,
5. platform mesh certification.

It also directs certification truth to generated platform artifacts instead of hand-authored broad
claims in Core.

## Tests Added

`tests/unit/docs/test_source_data_product_boundaries.py` now asserts that:

- `wiki/Mesh-Data-Products.md` does not use the broad `live-certified` wording,
- the wiki contains a compact proof-status table,
- the wiki names the two current trust telemetry snapshots,
- `contracts/trust-telemetry/README.md` and `REPOSITORY-ENGINEERING-CONTEXT.md` preserve the same
  scope boundary.

## Validation Evidence

Local evidence before commit:

- `python -m pytest tests\unit\test_trust_telemetry.py tests\unit\libs\portfolio-common\test_source_data_products.py tests\unit\scripts\test_source_data_product_contract_guard.py tests\unit\scripts\test_analytics_input_consumer_contract_guard.py tests\unit\docs\test_source_data_product_boundaries.py -q --tb=short` passed with 64 tests.
- `python scripts\source_data_product_contract_guard.py` passed.
- `python scripts\analytics_input_consumer_contract_guard.py` passed.
- `make domain-product-validate` passed, validating 1 producer declaration and 0 consumer declarations.
- `make quality-wiki-docs-gate` passed.
- `python C:\Users\Sandeep\projects\lotus-platform\codex\skills\lotus-readme-wiki-governance\scripts\audit_wiki_quality.py --wiki-dir wiki` passed.
- Scoped `ruff check` and `ruff format --check` passed for the edited docs test.
- `git diff --check` passed.
- `powershell -ExecutionPolicy Bypass -File C:\Users\Sandeep\projects\lotus-platform\automation\Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core` reported expected pre-publication drift for `Mesh-Data-Products.md` and `Operations-Runbook.md`, plus pre-existing `Outbox-Events.md` drift.
- Stranded-truth reconciliation found only active Dependabot branches:
  `origin/dependabot/github_actions/github-actions-02325a8da5` and
  `origin/dependabot/pip/python-runtime-b808a9fc65`.

## Downstream Compatibility

No runtime behavior, API route, response DTO, OpenAPI schema, Kafka topic, database schema, source
product declaration, or trust telemetry JSON changed.

The only change is documentation truth: active/catalog-visible/live-validated products are no
longer described as mesh certified unless platform certification evidence exists for the exact
product.

## Documentation And Wiki Decision

Docs/wiki changed because this issue is explicitly about product-truth posture:

- `wiki/Mesh-Data-Products.md`
- `contracts/trust-telemetry/README.md`
- `REPOSITORY-ENGINEERING-CONTEXT.md`
- `docs/architecture/CODEBASE-REVIEW-LEDGER.md`

Repo-local wiki source is updated in this slice. Publication remains post-merge per the Lotus wiki
publication rule.
