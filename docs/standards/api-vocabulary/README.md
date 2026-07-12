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
