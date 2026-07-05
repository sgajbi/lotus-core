# CR-1343 Supported Features Evidence Manifest

## Objective

Locally fix GitHub issue #618 by turning supported-feature publication from manually synchronized
docs/wiki prose into a guarded evidence manifest with drift checks.

## Finding

`docs/supported-features.md` and `wiki/Supported-Features.md` both described current capabilities,
but validation only checked for a few required terms. That could not detect unsupported capability
claims, missing implementation/test evidence, stale status values, missing fail-closed caveats, or
downstream ownership drift.

## Changes

- Added `contracts/supported-features/lotus-core-supported-features.v1.json` as the canonical
  supported-feature manifest.
- Added `scripts/supported_features_guard.py` and focused guard tests.
- Added `make supported-features-guard`.
- Wired the guard into `make architecture-guard`, `make quality-wiki-docs-gate`,
  `make docs-evidence-pack`, and `make lotus-core-validate`.
- Updated README, docs, wiki source, and repository context.

## Compatibility Impact

No runtime route, request DTO, response DTO, OpenAPI schema, database schema, Kafka contract,
metric name, Dockerfile, deployment topology, package import path, or public runtime behavior
changed. This is documentation, validation, and publication-governance hardening.

## Validation Evidence

Focused validation before commit:

```powershell
python -m pytest tests/unit/scripts/test_supported_features_guard.py tests/unit/scripts/test_generate_documentation_evidence_pack.py tests/unit/scripts/test_certify_lotus_core_app.py -q
python scripts/supported_features_guard.py
make quality-wiki-docs-gate
make architecture-guard
```

## Documentation And Wiki

Updated repo-authored documentation and wiki source. Wiki publication remains a post-merge action
through the governed `Sync-RepoWikis.ps1 -Publish -Repository lotus-core` flow.

## Guidance Decision

Repo-local context changed because supported-feature truth now has a new canonical manifest and
guard. No platform skill change is required; the existing backend delivery and codebase-review
skills already direct agents to promote repeatable documentation drift checks into deterministic
guards.
