# CR-1305 Domain Layer Contract Guard

## Scope

Issue cluster: GitHub issue #656.

This slice defines and enforces the repo-local pure domain-layer contract for private-banking
business logic.

## Objective

Document where domain models, value objects, business policies, calculations, validations,
state-transition rules, and private-banking vocabulary belong, then add an architecture guard that
prevents domain packages from importing framework, persistence, DTO, repository, client, consumer,
or settings modules unless explicitly allowlisted.

## Changes

1. Added `docs/standards/domain-layer-contract.md` with package conventions, allowed dependencies,
   disallowed dependencies, guard command, and representative implementations.
2. Added `scripts/domain_layer_guard.py` to scan service and shared domain packages.
3. Added `make domain-layer-guard`.
4. Wired `make architecture-guard` to run the domain-layer guard.
5. Added unit tests for allowed pure-domain imports, disallowed framework/repository imports, and
   explicit transitional allowlisting.
6. Updated repo-local engineering context and the codebase review ledger.

## Behavior And Compatibility

This is an architecture governance slice. It does not change runtime service behavior.

No route path, request DTO, response DTO, OpenAPI metadata, repository method signature, database
schema, Kafka topic, event payload, cost calculation, reconciliation finding, transaction field,
or source-data product output changed.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests\unit\scripts\test_domain_layer_guard.py -q`
2. `python scripts\domain_layer_guard.py`
3. `make architecture-guard`

Final scoped lint, format, docs, and diff evidence is recorded before commit.

## Documentation, Wiki, Context, And Skill Decision

Updated the codebase review ledger, repo-local engineering context, and domain-layer standard.

No wiki update is required because this slice adds repository-local architecture governance and
developer commands, not operator commands, supported product features, route behavior, or published
wiki truth.

No central Lotus skill change is required. The repeatable pattern is repo-local and enforced by the
new guard.

## Remaining Work

GitHub issue #656 is locally fixed for the domain-layer contract and representative workflow
acceptance criteria pending PR CI/QA and issue closure. Transitional Pydantic allowlists remain for
shared `portfolio_common.transaction_domain.*_models` and should be removed in future domain-model
extraction slices.
