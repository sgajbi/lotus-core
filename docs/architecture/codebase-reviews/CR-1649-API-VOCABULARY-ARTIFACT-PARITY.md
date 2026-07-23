# CR-1649 API Vocabulary Artifact Parity

## Status

Fixed locally on `fix/ci-evidence-stability`; protected CI, PR merge, exact-main validation, and
verified issue closure remain pending under GitHub issue #822.

## Objective and bounded scope

The existing `api-vocabulary-gate` validated a freshly generated in-memory inventory but did not
compare it with the tracked canonical artifact. A DTO description, example, type, route, control,
or catalog change could therefore leave
`docs/standards/api-vocabulary/lotus-core-api-vocabulary.v1.json` stale while protected CI passed.

The existing `--validate-only` command now validates both generated and committed structures, then
compares all semantic content without writing either source or tracked output. Only the top-level
`generatedAt` value is excluded because it is generation metadata rather than contract truth.
Failures report the first different JSON path and the governed regeneration command.

## Compatibility and no-change decisions

This is CI and contract-governance hardening only. Runtime API behavior, OpenAPI, event contracts,
database schema, migrations, and runtime topology are unchanged. The write path remains the
explicit `--output` command. The stable `--validate-only` and `make api-vocabulary-gate` entry
points remain unchanged, so workflow callers require no duplicated edits.

No repo-local wiki source changes are required. Existing wiki pages name the stable Make target but
do not describe the former in-memory-only behavior. The owning API-vocabulary README and repository
context carry the strengthened semantics.

## Same-pattern review

- The API route catalog already loads the tracked artifact and performs a non-mutating complete
  payload comparison through `generate_api_route_catalog.py --check`; it remains unchanged.
- The transaction capability catalog validator already compares its generated registry-owned
  fields with committed truth and rejects missing, duplicate, or drifted transaction codes; its
  authored product-lifecycle rows are intentionally not generator-owned.
- `generated_artifact_tracking_guard.py` governs disposable tracked output and is not a substitute
  for canonical-artifact parity.

No duplicate implementation or new issue is required within this bounded pattern.

## Validation

- Eleven warning-strict API-vocabulary tests pass, covering exact semantic parity, timestamp-only
  variation, description/type/example/route drift, malformed JSON, malformed catalog shape, focused
  diagnostics, byte-for-byte non-mutation, and truthful generated-only CLI output.
- `make api-vocabulary-gate` passes against the current tracked inventory and existing route catalog.
- Strict MyPy passes for the touched source; touched Ruff lint and format checks pass.
- `make quality-wiki-docs-gate` and `git diff --check` pass.

## Remaining delivery proof

Rebase after the preceding Core delivery lanes, run repository-native pre-merge gates, obtain
exact-head review and protected CI, merge with the governed rebase method, validate exact main,
record the no-wiki-change decision, close #822 only after QA verification, and safely remove the
feature branch/worktree after patch-equivalence proof.
