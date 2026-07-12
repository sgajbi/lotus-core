# CR-1324 Testability Architecture Guard

## Scope

Issue cluster: GitHub issue #629.

This slice adds an explicit architecture guard for the rule that protected domain, application,
port, policy, and pure reducer modules must remain testable without FastAPI, real databases, Kafka,
Redis, cloud SDKs, or downstream clients.

## Objective

Convert the repeated issue pattern from #624, #626, #627, #628, and the ports-layer work into a
repo-native guard so newly extracted business logic does not drift back to framework or runtime
dependencies.

## Changes

1. Added `docs/standards/testability-architecture-contract.json` with protected path globs,
   forbidden runtime imports, forbidden layer imports, forbidden symbols, and approved runtime
   composition path prefixes.
2. Added `scripts/testability_architecture_guard.py`, which loads the contract, scans protected
   modules with `ast`, and reports actionable file/line/rule/detail findings.
3. Added unit tests for allowed ports/fakes, forbidden FastAPI/DB/Kafka imports, forbidden
   repository/dependency imports, and invalid contract shape.
4. Wired `testability-architecture-guard` into `make architecture-guard`.
5. Added `docs/standards/testability-architecture-standard.md` with protected-layer rules, approved
   composition roots, and a fake-port use-case example.

## Behavior And Compatibility

No route path, request DTO, response DTO, OpenAPI metadata, Kafka topic, event payload, database
schema, repository SQL, metric name, runtime wiring, or deployment topology changed.

The guard is enforceable for the current protected set and intentionally does not claim legacy
service modules that still take `AsyncSession` are complete. Those modules should be added to the
contract as they are migrated into domain/application/port/policy boundaries.

## Validation Evidence

Focused local validation:

1. `python -m pytest tests/unit/scripts/test_testability_architecture_guard.py -q`
2. `python scripts/testability_architecture_guard.py`
3. `python -m ruff check scripts/testability_architecture_guard.py tests/unit/scripts/test_testability_architecture_guard.py --ignore E501,I001`
4. `python -m ruff format --check scripts/testability_architecture_guard.py tests/unit/scripts/test_testability_architecture_guard.py`

Aggregate validation before commit:

1. `make architecture-guard`
2. `python scripts/wiki_validation_guard.py`
3. `git diff --check`

All listed commands passed locally before commit.

## Documentation, Wiki, Context, And Skill Decision

Updated repo-local standards, architecture overview, codebase review ledger, and repo context.

No wiki update is required because this slice changes internal engineering governance and guard
coverage without changing operator-facing commands, public API behavior, supported features, or
published wiki truth.

No platform skill source change is required in this slice because the existing backend delivery
skill already directs agents to use architecture guards, ports/adapters, fake-port tests, and repo
context. The repo-local contract is the actionable implementation detail.

## Remaining Work

GitHub issue #629 is locally fixed for the explicit testability contract, custom guard, approved
composition roots, fake-port guidance, CI/architecture-lane wiring, and actionable violation output
pending PR CI/QA and issue closure.

Future slices should expand `protectedPathGlobs` as legacy service modules move behind use cases,
ports, and pure policy modules.
