# CR-324 Shared Lineage Whitespace Normalization Fence

## Scope
Shared lineage normalization in `portfolio_common.logging_utils`.

## Finding
`normalize_lineage_value(...)` only treated exact `""` and `"<not-set>"` as unset. Whitespace-only values or padded sentinel values could therefore leak through as fake correlation/request/trace ids across HTTP middleware, logging, and repository lineage persistence.

## Fix
Changed shared lineage normalization to:
- strip surrounding whitespace
- treat empty-after-strip values as unset
- treat `<not-set>` case-insensitively after strip as unset
- return trimmed real lineage values

## Evidence
- `python -m pytest tests/unit/libs/portfolio-common/test_logging_utils.py tests/unit/services/ingestion_service/test_request_metadata.py -q`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/logging_utils.py tests/unit/libs/portfolio-common/test_logging_utils.py`
