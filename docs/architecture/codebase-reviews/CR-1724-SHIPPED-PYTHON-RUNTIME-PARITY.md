# CR-1724: Shipped Python Runtime Parity

## Invariant

The dense in-process validation suites, language tooling, dependency replay, and service images use
the Python minor version that Core ships. Version drift must fail before merge.

## Finding

All service images and Windows dependency-closure jobs used Python 3.11, while the five GitHub
workflows, Ruff, and mypy used Python 3.12. Container smoke and E2E lanes exercised the shipped
runtime, but unit, integration, coverage, lint, and type analysis did not.

## Correction

- record Python 3.11 in the standard root `.python-version` authority;
- align all workflow host interpreters, Ruff, mypy, and the required-check environment policy;
- enforce parity across the five workflows, every Compose service Dockerfile, the package floor,
  Ruff, mypy, and Windows lock replay in the workflow-governance suite; and
- publish one local setup and troubleshooting story for Python 3.11.

The production images, dependency locks, package floor, API, financial behavior, schema, and
runtime topology are unchanged. The protected Feature, PR, and Main lanes provide the behavioral
compatibility proof on the shipped interpreter.

## Evidence Required For Closure

1. focused workflow-policy and runtime-version governance tests;
2. full lint, typecheck, unit, and workflow-governance gates under repository rules;
3. protected exact-head checks and resolved review findings;
4. per-revision exact-main Main Releasability evidence for every rebase-landed commit;
5. wiki publication/parity and clean branch/worktree state.
