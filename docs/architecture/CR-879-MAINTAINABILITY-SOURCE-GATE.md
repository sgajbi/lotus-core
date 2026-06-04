# CR-879 Maintainability Source Gate

Date: 2026-06-02

## Scope

Promote the source maintainability baseline into a bounded quality gate without hiding existing
complexity hotspots.

## Finding

`python -m radon mi src -s` reports no D/E/F maintainability modules in production source. Existing
C-ranked hotspots remain, including `portfolio_common/openapi_enrichment.py` and selected
query-service repository/service modules. Separately, Xenon still reports F-ranked complexity
blocks, so broad complexity enforcement is not yet truthful.

## Decision

Add a repo-native maintainability gate:

```powershell
python scripts/maintainability_gate.py src
```

The gate parses `radon mi --json` output and fails only when a source module drops below C. This
keeps the current no-D/E/F maintainability baseline regression-free while leaving existing C
hotspots visible for targeted refactor slices.

## Follow-Up

1. Reduce existing C-ranked maintainability hotspots by domain priority.
2. Continue measuring complexity separately; do not promote broad Xenon complexity enforcement
   until current F-ranked complexity blocks are refactored or explicitly governed.
3. Keep the maintainability gate source-scoped; test and generated-code maintainability cleanup
   should be handled in separate focused batches.

## Evidence

- `make quality-maintainability-gate` => no source modules below C
- `python -m pytest tests/unit/scripts/test_maintainability_gate.py -q` => focused gate tests pass
- `.github/workflows/quality-baseline.yml` includes `maintainability-gate`
- No wiki change: this is quality-gate evidence, not operator-facing product behavior.
