# CR-295: Reference-data bookkeeping failure proof

Date: 2026-03-14

## Summary
- Added integration proof that the reference-data ingestion path behaves truthfully when the durable
  upsert succeeds but later `mark_queued(...)` bookkeeping fails.

## Problem
- `CR-294` hardened both Kafka-backed and reference-data ingress routers.
- But only the Kafka-backed transaction path had end-to-end proof.
- That left the reference-data side relying on code-shape confidence rather than runtime evidence.

## Change
- Extended the ingestion router integration harness with a fake reference-data ingestion service.
- Added an integration proof for `/ingest/benchmark-definitions` showing that when:
  - the reference-data upsert succeeds
  - and `mark_queued(...)` fails afterward
- the router now:
  - returns `INGESTION_JOB_BOOKKEEPING_FAILED`
  - leaves the job non-terminal
  - records `failure_phase="persist_bookkeeping"`
  - and preserves the already-persisted reference data

## Why this matters
- This closes the evidence gap for the non-Kafka ingress variant.
- Operators now have proof that a bookkeeping failure after durable persist is not misreported as if
  the persist itself failed.

## Evidence
- Integration proof:
  - `tests/integration/services/ingestion_service/test_ingestion_routers.py`
  - proves a benchmark-definition ingest request with forced `mark_queued(...)` failure:
    - returns `INGESTION_JOB_BOOKKEEPING_FAILED`
    - keeps the job non-terminal
    - records `persist_bookkeeping` failure history
    - preserves the persisted benchmark definition payload

## Validation
- `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -k "bookkeeping_failure_after_publish or bookkeeping_failure_after_persist or record_failure_observation or job_bookkeeping" -q`
- `python -m ruff check tests/integration/services/ingestion_service/test_ingestion_routers.py`

## Follow-up
- The next worthwhile move is to look for another remediation or operator path where durable work can
  succeed before local bookkeeping, and add the same truth-preserving split if it is still missing.
