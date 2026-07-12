# CR-876: Vulture Source Dead-Code Regression Gate

Status: Hardened on 2026-06-02.

## Finding

The quality scorecard still marked dead-code analysis as not locally measured. Vulture is now
available locally, and the production-source scan reported high-confidence findings:

1. intentional but unnamed signal-handler frame parameters in worker consumer managers,
2. an intentional but unnamed outbox delivery callback id parameter.

The broader `python -m vulture src tests --min-confidence 80` report remains noisy because many
test fixtures are intentionally requested by parameter name, including legacy tests that live under
`src`.

## Change

Cleaned the source baseline by:

1. marking callback-only signal frame parameters as `_frame`,
2. marking the callback-only outbox delivery id as `_replayed_outbox_id`.

Added:

1. `make quality-vulture-source-gate`,
2. a dedicated `Quality Baseline / Vulture Source Dead-Code Gate` workflow job.

The enforced command is:

```bash
python -m vulture src --exclude "*/tests/*" --min-confidence 80
```

## Boundary Preserved

This change preserves:

1. runtime signal-handler compatibility,
2. outbox delivery callback compatibility,
3. API contracts,
4. database schema,
5. report-only posture for the broader test-fixture Vulture baseline.

## Wiki Decision

No repo-local `wiki/` source update is included. This is source dead-code cleanup and CI
quality-gate governance recorded in the repo-local quality reports and architecture review ledger;
it does not change operator-facing runtime behavior.

## Validation

Local validation passed for the slice:

1. `make quality-vulture-source-gate`,
2. representative consumer-manager runtime tests,
3. `make quality-ruff-gate`,
4. `make quality-ruff-format-gate`,
5. `make quality-bandit-gate`,
6. `make typecheck`,
7. workflow YAML parsing,
8. `git diff --check`.
