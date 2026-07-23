# lotus-core API Vocabulary Inventory

This folder stores the generated RFC-0067 API vocabulary inventory for `lotus-core`.

## Regenerate

```powershell
python scripts/quality/api_vocabulary_inventory.py `
  --output docs/standards/api-vocabulary/lotus-core-api-vocabulary.v1.json
```

## Validate

```powershell
python scripts/quality/api_vocabulary_inventory.py --validate-only
```

Validation is non-mutating and fail-closed. It validates freshly generated and committed inventory
structure, then requires semantic parity while ignoring only the volatile top-level `generatedAt`
timestamp. A stale description, type, example, route, control, or catalog entry fails with the first
different JSON path and the governed regeneration command.
