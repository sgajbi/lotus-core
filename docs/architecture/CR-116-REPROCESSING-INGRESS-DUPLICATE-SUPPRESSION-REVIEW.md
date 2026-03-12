## CR-116: Reprocessing ingress duplicate suppression

### Scope
- ingestion write-plane reprocessing router

### Finding
The replay API consumer and repository were already being hardened for deterministic ordering and duplicate suppression, but the ingress router still accepted duplicate transaction IDs and published duplicate `transactions_reprocessing_requested` commands before the downstream layers saw them.

### Change
- Deduplicated caller-provided `transaction_ids` at ingress while preserving first-seen order.
- Used the deduplicated list consistently for rate limiting, job accepted count, persisted request payload, publication, and failure bookkeeping.
- Added router-level integration coverage proving duplicate IDs produce a single command per canonical transaction.

### Follow-up
Keep replay request deduplication at the earliest boundary possible. Downstream replay consumers may still defend themselves, but ingress should not knowingly inject duplicate commands.

### Evidence
- `src/services/ingestion_service/app/routers/reprocessing.py`
- `tests/integration/services/ingestion_service/test_ingestion_routers.py`
- `python -m pytest tests/integration/services/ingestion_service/test_ingestion_routers.py -k reprocess_transactions -q`
