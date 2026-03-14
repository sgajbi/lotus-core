# CR-296: Ingestion shutdown flush truth

Date: 2026-03-14

## Summary
- Hardened ingestion-service shutdown so it no longer logs Kafka producer flush success when Kafka
  still reports undelivered messages.

## Problem
- `src/services/ingestion_service/app/main.py` always logged:
  - `Kafka producer flushed successfully.`
- But it ignored the return value of:
  - `producer.flush(timeout=5)`
- A positive undelivered count meant shutdown could still log success even though Kafka had not
  confirmed delivery of all buffered messages.

## Change
- Wrapped shutdown flush handling in explicit success/failure branches.
- The ingestion service now:
  - logs success only when `flush(timeout=5) == 0`
  - logs an error when `flush(timeout=5) > 0`
  - logs an exception if the flush itself raises
- Added an ingestion app contract test proving the timeout branch suppresses the false success log.

## Why this matters
- Shutdown is part of the delivery story.
- If buffered messages remain undelivered, operators need a truthful signal instead of a clean-shutdown
  success message.
- This keeps service lifecycle behavior aligned with the stricter delivery-accounting standard we have
  been applying elsewhere.

## Evidence
- Integration proof:
  - `tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py`
  - proves that when the shutdown flush returns a positive undelivered count:
    - startup and shutdown still complete
    - success is not logged
    - the timeout/error log is emitted instead

## Validation
- `python -m pytest tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py -k "startup_when_kafka_init_fails or shutdown_flush_timeout_truth" -q`
- `python -m ruff check src/services/ingestion_service/app/main.py tests/integration/services/ingestion_service/test_ingestion_main_app_contract.py`

## Follow-up
- The next worthwhile move is to review any remaining service lifecycle hook that still treats
  best-effort producer flush as unconditional success, especially outside the ingestion app.
