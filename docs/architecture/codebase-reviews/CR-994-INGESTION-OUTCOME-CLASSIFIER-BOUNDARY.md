# CR-994: Ingestion Outcome Classifier Boundary

Date: 2026-06-05

## Scope

Split ingestion outcome classification into count validation, terminal-failure calculation, partial
outcome predicate, and valid-outcome policy helpers without changing accepted, partially accepted,
quarantined, rejected, empty, source-batch fingerprint, or invalid-count behavior.

## Finding

`classify_ingestion_outcome` mixed non-negative count validation, terminal-failure aggregation,
accepted-plus-failure classification, accepted classification, quarantined classification, rejected
classification, and empty fallback in one B-ranked helper. This made RFC-0083 ingestion evidence
policy harder to review as source-data ingestion outcomes expanded.

## Action

Added focused helpers for count validation, terminal-failure counting, partial-outcome detection,
and valid-outcome classification. The public classifier now validates the counts and delegates to
explicit outcome policy helpers.

## Result

`classify_ingestion_outcome` improved from `B (6)` to `A (1)`. All functions/classes in
`ingestion_evidence.py` now report A-ranked cyclomatic complexity, and the module remains A-ranked
maintainability at `A (37.92)`.

## Evidence

- `python -m pytest tests\unit\libs\portfolio-common\test_ingestion_evidence.py -q`
  => 18 passed
- `python -m ruff check src\libs\portfolio-common\portfolio_common\ingestion_evidence.py tests\unit\libs\portfolio-common\test_ingestion_evidence.py`
  => all checks passed
- `python -m ruff format --check src\libs\portfolio-common\portfolio_common\ingestion_evidence.py tests\unit\libs\portfolio-common\test_ingestion_evidence.py`
  => 2 files already formatted
- `python -m radon cc src\libs\portfolio-common\portfolio_common\ingestion_evidence.py -s`
  => `classify_ingestion_outcome` `A (1)` and all functions/classes A-ranked
- `python -m radon mi src\libs\portfolio-common\portfolio_common\ingestion_evidence.py -s`
  => `ingestion_evidence.py` `A (37.92)`
- `python -m radon raw src\libs\portfolio-common\portfolio_common\ingestion_evidence.py`
  => 105 SLOC / 95 LLOC
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal ingestion evidence helper refactor that
preserves source-data outcome semantics and operator-facing documentation truth.
