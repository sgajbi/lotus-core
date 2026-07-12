## CR-113: Replay API correlation header hygiene

### Scope
- replay API publication path in `ReprocessingRepository.reprocess_transactions_by_ids(...)`

### Finding
The replay API boundary now preserves deterministic ordering and deduplicates duplicate transaction ids, but it still treated the default `correlation_id_var` value `"<not-set>"` as a real correlation header. That could republish replay messages with poisoned lineage metadata even though no real correlation id had been established.

### Change
- Normalized `"<not-set>"` to `None` before constructing Kafka headers.
- Added unit coverage proving replay publication omits the correlation header when the ambient context is unset.

### Follow-up
Apply the same normalization rule to any remaining publication paths that still convert ambient correlation context directly into durable headers.

### Evidence
- `src/libs/portfolio-common/portfolio_common/reprocessing_repository.py`
- `tests/unit/libs/portfolio-common/test_reprocessing_repository.py`
- `python -m pytest tests/unit/libs/portfolio-common/test_reprocessing_repository.py -q`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/reprocessing_repository.py tests/unit/libs/portfolio-common/test_reprocessing_repository.py`
