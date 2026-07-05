# CR-1350 Front-Door Sync Governance

Date: 2026-07-05

## Objective

Fix GitHub issue #613 by adding a deterministic README/wiki front-door synchronization contract and
guard.

The objective is to reduce design-time complexity for engineers, operators, downstream owners, and
agents by making the repository's front doors explicit, testable, and aligned with durable source
truth.

## Findings

`lotus-core` had multiple front doors for current-state truth:

- `README.md`
- `wiki/Home.md`
- `wiki/_Sidebar.md`
- repository context
- architecture docs and catalogs
- API route catalog and route-family registry
- RFC status ledger
- supported-features material
- runbooks and validation evidence
- PR documentation acceptance checklist

Those surfaces were individually useful, but there was no single repo-native contract defining
which files are canonical sources versus summaries, which README/wiki/sidebar references must
exist, and which PR documentation/no-wiki-change decision terms must remain present.

## Changes

Added `docs/standards/front-door-sync.v1.json` to define canonical sources, summary/navigation
surfaces, required README links, wiki home links, wiki sidebar pages, PR template documentation
terms, and the update checklist for front-door truth changes.

Added `scripts/front_door_sync_guard.py` to fail when required front-door files, links, sidebar
entries, or PR documentation/no-doc-change terms drift.

Added focused tests for accepted contracts, missing README links, missing sidebar pages, and missing
PR template terms.

Wired `make front-door-sync-guard` into `quality-wiki-docs-gate`, lint, and documentation evidence
generation. Updated README, Validation/CI wiki source, repo context, and this codebase-review
ledger.

## Compatibility

This is documentation and validation only.

No route path, request DTO, response DTO, OpenAPI schema, database schema, Kafka contract, metric
name, runtime topology, Dockerfile, package import path, or public runtime behavior changed.

## Validation Evidence

Focused validation before commit:

- `python scripts/front_door_sync_guard.py`
- `python -m pytest tests/unit/scripts/test_front_door_sync_guard.py tests/unit/scripts/test_generate_documentation_evidence_pack.py -q`
- `python -m ruff check scripts/front_door_sync_guard.py tests/unit/scripts/test_front_door_sync_guard.py scripts/generate_documentation_evidence_pack.py tests/unit/scripts/test_generate_documentation_evidence_pack.py --ignore E501,I001`
- `python -m ruff format --check scripts/front_door_sync_guard.py tests/unit/scripts/test_front_door_sync_guard.py scripts/generate_documentation_evidence_pack.py tests/unit/scripts/test_generate_documentation_evidence_pack.py`
- `make docs-evidence-pack`
- `make quality-wiki-docs-gate`
- `python C:\Users\Sandeep\.codex\skills\lotus-readme-wiki-governance\scripts\audit_wiki_quality.py --wiki-dir wiki --changed-page Validation-and-CI.md`
- `git diff --check`

`Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core` reported expected pre-merge publication
drift across the existing repo-authored wiki source, including `Validation-and-CI.md`. Publish wiki
source after merge with the governed wiki sync flow.

## Docs, Wiki, And Context

Wiki source changed in `wiki/Validation-and-CI.md`; publish after merge with the governed wiki sync
flow.

No Lotus skill update is required for this slice. Existing README/wiki governance, backend
delivery, CI enforcement, and codebase-review skills already require front-door truth and
no-doc-change decisions. The repo-local sync guard is the reusable control that prevents this
specific drift pattern from recurring.
