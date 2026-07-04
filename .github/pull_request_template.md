## Summary
- 

## Why
- 

## Scope
- [ ] Single RFC/slice scope
- [ ] No unrelated refactors mixed in

## Validation (local)
- [ ] `make lint`
- [ ] `make typecheck`
- [ ] `make test-unit`
- [ ] Additional targeted checks for changed area

## CI Expectations
- [ ] Fast PR gates are green
- [ ] Heavy gates run in scheduled/manual tier where applicable

## Governance/Docs
- [ ] RFC/docs updated where behavior or standards changed
- [ ] API/OpenAPI/vocabulary updates included if contract changed
- [ ] Runtime-boundary decision record/catalog entry included for new deployables, or no-runtime-split rationale recorded for in-process-only modularity

## Post-Merge Hygiene
- [ ] Delete remote feature branch
- [ ] Delete local feature branch
- [ ] Sync local main with origin/main (`local = remote = main`)
