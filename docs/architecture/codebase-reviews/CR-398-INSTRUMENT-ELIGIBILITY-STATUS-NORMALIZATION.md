# CR-398: Instrument Eligibility Status Normalization

Date: 2026-05-28

## Scope

Query-service `InstrumentEligibilityProfile` source-data product record status fields.

## Finding

Instrument eligibility records uppercased `eligibility_status`, `product_shelf_status`, and
`quality_status` without trimming. Padded source values such as ` restricted ` or ` accepted `
could leak padded control codes into downstream eligibility consumers even when the aggregate
supportability status remained correct.

## Change

Reused the query-service control-code normalizer for instrument eligibility record status fields.
Record-level eligibility, product shelf, and quality statuses now emit canonical trimmed uppercase
codes. Updated direct coverage so padded lower-case restricted eligibility still returns canonical
`RESTRICTED` shelf/eligibility status and `ACCEPTED` quality status.

## Evidence

Commands:

1. `python -m pytest tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m pytest tests/unit/services/query_service/services -q`
3. `python -m ruff check src/services/query_service/app/services/integration_service.py tests/unit/services/query_service/services/test_integration_service.py`

## Closure

Status: Hardened.

No API route, OpenAPI, wiki source, or platform contract change was required. This is a
source-data product contract hygiene and downstream eligibility-consumer correctness slice.
