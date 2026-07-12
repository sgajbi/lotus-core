# CR-441: Missing FX Dependency Security-ID Normalization

Date: 2026-05-28

## Scope

Query-service operations repository missing historical FX dependency evidence.

## Finding

Missing historical FX dependency samples selected and returned transaction `security_id` values
directly from persisted rows. Whitespace drift could leak non-canonical identifiers into operator
remediation evidence for FX-rate gaps.

That is a supportability and calculation-readiness risk because operators use this evidence to
identify which transaction/security combinations need historical FX enrichment before valuation and
reporting can be trusted.

## Change

Reused the operations repository security identifier expression when building missing-FX sample
records. The sample query now selects `trim(transactions.security_id)` and returned records are
normalized before being exposed through the summary object.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
2. `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
3. `python -m pytest tests/unit/services/query_service/repositories -q`
4. `python -m pytest tests/unit/services/query_service/services -q`
5. `git diff --check`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is an
operations-readiness hardening slice that prevents padded source identifiers from polluting
missing-FX remediation evidence.
