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
- [ ] Documentation impact reviewed across README, architecture docs, API catalog/OpenAPI/vocabulary, RFCs, runbooks, supported-features, wiki source, repository context, and platform context
- [ ] Updated docs are linked here, or an explicit no-doc-change rationale is recorded:
- [ ] Route, contract, supported-feature, operational, security, validation-lane, and service-boundary changes include updated documentation evidence or a no-doc-change rationale
- [ ] Runtime-boundary decision record/catalog entry included for new deployables, or no-runtime-split rationale recorded for in-process-only modularity
- [ ] Wiki source changes list `wiki/` paths and the post-merge `Sync-RepoWikis.ps1 -Publish -Repository lotus-core` evidence plan

## Post-Merge Hygiene
- [ ] Delete remote feature branch
- [ ] Delete local feature branch
- [ ] Sync local main with origin/main (`local = remote = main`)
