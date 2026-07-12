# CR-1272 Clean Generated Artifacts Policy

- Date: 2026-07-04
- Status: Hardened locally
- GitHub issues: #699, #649 pattern review

## Objective

Make local cleanup match the repository-generated artifact and cache policy without relying on an
opaque inline `Makefile` command.

## Expected Improvement

`make clean` now delegates to `scripts/clean_generated_artifacts.py`, a reviewed, test-backed
cleanup utility with an explicit repo-root-scoped allowlist. The policy removes ignored local
caches, Python bytecode, build/package byproducts, coverage files, and generated `output/`
evidence artifacts while preserving source, docs, wiki source, migrations, contracts, `.git`,
virtual environments, and dependency directories.

This hardens the reusable platform pattern for future agents: cleanup behavior belongs in a safe
script with focused tests, not an inline shell or Python one-liner.

## Pattern Review

- #699 is valid: the previous `make clean` removed only a narrow subset of ignored artifacts and
  left common disposable cache/build/evidence outputs behind.
- #649's original tracked `src/services/query_service/build/lib` symptom is no longer present on
  current `main`; `git ls-files src/services/query_service/build/lib` returns zero files. The
  generated build-tree risk remains covered by `.gitignore`, guard exclusions, and the new cleanup
  script.

## Compatibility Impact

No API, OpenAPI, database schema, runtime topology, Kafka topic, dependency, or public contract
changed. The behavior change is limited to local cleanup: `make clean` now removes additional
ignored disposable artifacts, including generated `output/` evidence. Regenerate evidence through
the repo-native validation commands when needed.

## Tests Added

- `tests/unit/scripts/test_clean_generated_artifacts.py`
  - nested cache and bytecode cleanup
  - build/package byproduct cleanup
  - generated `output/` cleanup
  - protected `.git`, `.venv`, `node_modules`, docs, wiki, contracts, migrations, and source
    preservation
  - dry-run behavior
  - outside-repository deletion refusal

## Documentation Decision

Updated:

- `README.md`
- `REPOSITORY-ENGINEERING-CONTEXT.md`
- `docs/architecture/CODEBASE-REVIEW-LEDGER.md`

No wiki source change: this is a local developer/agent cleanup command and does not change
operator-facing runtime behavior, API support, source-data product truth, or public feature claims.

## Validation Evidence

- `python -m pytest tests/unit/scripts/test_clean_generated_artifacts.py tests/unit/scripts/test_source_contract_guards.py -q`
  passed with 6 tests.
- `python -m ruff check scripts/clean_generated_artifacts.py tests/unit/scripts/test_clean_generated_artifacts.py --ignore E501,I001`
  passed.
- `python -m ruff format --check scripts/clean_generated_artifacts.py tests/unit/scripts/test_clean_generated_artifacts.py`
  passed after formatting the new script.
- `python scripts/clean_generated_artifacts.py --dry-run`
  reported 177 governed generated artifacts, including current disposable caches, bytecode,
  `output`, service `*.egg-info`, and untracked `src/services/query_service/build`.
- `make -n clean`
  confirmed the Make target delegates to `python scripts/clean_generated_artifacts.py`.
- `git diff --check`
  passed with CRLF normalization warnings only.
- `make lint`
  passed, including the new cleanup script lint/format checks and existing repository guards.
- `make quality-wiki-docs-gate`
  passed.
