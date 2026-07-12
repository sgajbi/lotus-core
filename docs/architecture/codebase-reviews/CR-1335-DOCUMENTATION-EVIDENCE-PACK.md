# CR-1335 Documentation Evidence Pack

## Scope

Issue cluster: GitHub issue #622.

## Objective

Give release, PR, and demo reviewers one machine-readable documentation evidence pack for
README, wiki, API, RFC, runbook, and supported-feature claims instead of scattered commands.

## Changes

1. Added `scripts/generate_documentation_evidence_pack.py`.
2. Added `make docs-evidence-pack`, which writes
   `output/documentation-evidence/documentation-evidence-pack.json`.
3. The evidence manifest records command, UTC timestamp, git SHA, runtime profile, status,
   generated artifact paths, affected documentation surfaces, and per-check details.
4. The pack includes README link validation, wiki validation, API vocabulary artifact generation,
   RFC-0083 closure ledger checks, supported-feature truth checks, and runbook validation.
5. Added focused unit coverage and concise README, supported-features, wiki, and repo-context
   pointers.

## Behavior And Compatibility

No runtime behavior, route path, request DTO, response DTO, OpenAPI schema, database schema, Kafka
contract, metric, deployment topology, package import path, or public API behavior changed.

The new target is a documentation/release evidence command. It does not replace
`make lotus-core-validate`; it complements that app-level validation artifact with documentation
claim evidence.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/scripts/test_generate_documentation_evidence_pack.py -q`
2. `make docs-evidence-pack`
3. `python scripts/wiki_validation_guard.py`
4. `python -m ruff check scripts/generate_documentation_evidence_pack.py tests/unit/scripts/test_generate_documentation_evidence_pack.py --ignore E501,I001`
5. `python -m ruff format --check scripts/generate_documentation_evidence_pack.py tests/unit/scripts/test_generate_documentation_evidence_pack.py`
6. `git diff --check`

## Documentation, Wiki, Context, And Skill Decision

Updated README, supported-features docs, repo-local wiki source, repo context, and the review
ledger because documentation/release evidence truth changed.

Wiki source changed and must be published after merge to `main` using the governed platform wiki
sync command.

No platform skill source change is required. The durable lesson is implemented as a repo-native
command and concise context pointers rather than more passive prose.

## Remaining Work

GitHub issue #622 is locally fixed for a machine-readable documentation evidence pack pending PR
CI/QA, wiki publication after merge, and issue closure.
