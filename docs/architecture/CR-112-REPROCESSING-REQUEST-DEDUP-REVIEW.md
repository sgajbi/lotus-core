## CR-112: Reprocessing request duplicate-ID deduplication

### Scope
- replay API request handling in `ReprocessingRepository.reprocess_transactions_by_ids(...)`

### Finding
CR-111 fixed deterministic ordering for multi-transaction replay requests, but the replay API still accepted duplicate transaction IDs and would republish the same canonical transaction multiple times in one request. That is a real replay-correctness gap, not just an inefficiency.

### Change
- Deduplicated caller-provided `transaction_ids` while preserving first-seen order before querying and republishing.
- Added unit coverage proving duplicate IDs in the request produce one republish per canonical transaction, in deterministic first-seen order.

### Follow-up
Keep replay request handling idempotent at the API boundary. If future replay workflows need explicit duplicate semantics, that should be a separate contract rather than falling out of raw input lists.

### Evidence
- `src/libs/portfolio-common/portfolio_common/reprocessing_repository.py`
- `tests/unit/libs/portfolio-common/test_reprocessing_repository.py`
- `python -m pytest tests/unit/libs/portfolio-common/test_reprocessing_repository.py -q`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/reprocessing_repository.py tests/unit/libs/portfolio-common/test_reprocessing_repository.py`
