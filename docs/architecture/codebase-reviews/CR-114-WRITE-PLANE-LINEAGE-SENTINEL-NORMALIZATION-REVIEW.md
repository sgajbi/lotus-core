## CR-114: Write-plane lineage sentinel normalization

### Scope
- ingestion write-plane Kafka header construction
- shared request-lineage echo helper for ingestion and replay-control acknowledgements

### Finding
The write-plane still treated the default context sentinel `"<not-set>"` as real lineage metadata. That could leak into Kafka headers and acknowledgement/request-lineage payloads even when no real correlation, request, or trace id had been established.

### Change
- Normalized `"<not-set>"` to `None` in `IngestionService._get_headers(...)`.
- Normalized the same sentinel in `get_request_lineage()` so acknowledgement and control-plane request metadata stop echoing fake ids.
- Added unit coverage for both the Kafka-header path and the shared request-lineage helper.

### Follow-up
Apply the same sentinel-normalization rule to any other remaining API-layer helpers that echo ambient lineage context directly into durable or client-visible metadata.

### Evidence
- `src/services/ingestion_service/app/services/ingestion_service.py`
- `src/services/ingestion_service/app/request_metadata.py`
- `tests/unit/services/ingestion_service/services/test_ingestion_service.py`
- `tests/unit/services/ingestion_service/test_request_metadata.py`
- `python -m pytest tests/unit/services/ingestion_service/services/test_ingestion_service.py tests/unit/services/ingestion_service/test_request_metadata.py -q`
