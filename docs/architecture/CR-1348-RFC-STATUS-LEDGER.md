# CR-1348 RFC Status Ledger

Date: 2026-07-05

## Objective

Fix GitHub issue #615 by making RFC status truth machine-readable and guarded across the current
`lotus-core` RFC surfaces:

- core RFC files and `docs/RFCs/RFC-INDEX.md`
- transaction RFC/specification documents
- architecture RFC material
- operations RFC playbooks

The objective is to reduce design-time complexity and stale-doc risk without changing runtime
behavior or downstream contracts.

## Findings

RFC status and implementation posture were previously spread across Markdown indexes, transaction
specification prose, architecture notes, operations docs, wiki pages, and local review memory. That
made it easy to add or edit an RFC file without durable metadata for owner, status, affected
services/routes/data models, implementation evidence, test evidence, wiki links, supported-feature
claims, canonical registry links, or supersession/deprecation relationships.

The repeated pattern from related documentation-governance issues is that prose-only truth does not
scale in a large repository. Current-state claims need a small, deterministic, repo-native guard.

## Changes

Added `docs/standards/rfc-status-ledger.v1.json` as the governed RFC status inventory. Each entry
records RFC identity, family, path, status, owner, affected services/routes/data models,
implementation references, test evidence, docs/wiki links, supported-feature references, canonical
registry references, supersession metadata, and status rationale.

Added `scripts/rfc_status_ledger_guard.py` to discover RFC documents and fail when ledger metadata
is missing, stale, duplicated, malformed, or missing transaction-specific links to
`portfolio_common.transaction_type_registry` and `docs/supported-features.md`.

Added focused unit tests for complete metadata, missing RFC metadata, stale metadata, missing
transaction registry links, broken path references, and implemented entries without evidence.

Wired the guard into `make rfc-status-ledger-guard`, `quality-wiki-docs-gate`, lint formatting
coverage, and the documentation evidence pack.

Updated README, the core RFC index, transaction RFC README, wiki RFC index, repository engineering
context, and this codebase-review ledger.

## Compatibility

This is documentation and validation only.

No route path, request DTO, response DTO, OpenAPI schema, database schema, Kafka contract, metric
name, runtime topology, Dockerfile, package import path, or public runtime behavior changed.

## Validation Evidence

Focused validation before commit:

- `python scripts/rfc_status_ledger_guard.py`
- `python -m pytest tests/unit/scripts/test_rfc_status_ledger_guard.py tests/unit/scripts/test_generate_documentation_evidence_pack.py -q`
- `python -m ruff check scripts/rfc_status_ledger_guard.py tests/unit/scripts/test_rfc_status_ledger_guard.py scripts/generate_documentation_evidence_pack.py tests/unit/scripts/test_generate_documentation_evidence_pack.py --ignore E501,I001`
- `python -m ruff format --check scripts/rfc_status_ledger_guard.py tests/unit/scripts/test_rfc_status_ledger_guard.py scripts/generate_documentation_evidence_pack.py tests/unit/scripts/test_generate_documentation_evidence_pack.py`
- `make quality-wiki-docs-gate`
- `make docs-evidence-pack`
- `python C:\Users\Sandeep\.codex\skills\lotus-readme-wiki-governance\scripts\audit_wiki_quality.py --wiki-dir wiki --changed-page RFC-Index.md --changed-page Validation-and-CI.md`
- `make lint`
- `git diff --check`

`Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core` reported expected pre-merge publication
drift across the existing repo-authored wiki source, including the two pages changed in this slice.
Publish wiki source after merge with the governed wiki sync flow.

## Docs, Wiki, And Context

Wiki source changed in `wiki/RFC-Index.md` and `wiki/Validation-and-CI.md`; publish after merge
with the governed wiki sync flow.

No Lotus skill update is required for this slice. Existing RFC review, README/wiki governance,
backend delivery, CI enforcement, and codebase-review skills already require durable metadata,
guarded docs truth, and evidence-backed closure. The repo-local guard is the reusable control that
prevents this specific RFC metadata drift from recurring.
