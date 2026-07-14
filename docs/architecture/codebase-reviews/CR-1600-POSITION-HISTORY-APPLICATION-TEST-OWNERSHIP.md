# CR-1600: Position History Application Test Ownership

## Objective

Place position-history orchestration tests beside the application use-case boundary instead of in
a mixed position folder shared with domain policy tests.

## Finding

`test_position_history_processor.py` validates framework-neutral application orchestration through
repository, state-store, and observer ports. It remained under the generic `position` test folder,
which obscured its layer and mixed use-case behavior with pure position domain policies. Critical-
path and risk coverage contracts also pinned that stale location.

## Change

1. Moved and renamed the suite to `application/test_position_history.py`.
2. Added target application-owner and retired mixed-path assertions.
3. Reconciled critical-path and risk-based coverage evidence paths.
4. Extended repository-local test-layout guidance for position-history orchestration.

## Measurable Improvement

- Removed one application test module from the mixed `position` folder.
- Reduced mixed position-root test modules from three to two.
- Added one application-owner and one retired-path regression assertion.
- Kept all position-history replay, stale epoch, lock ordering, coalescing, and generation rearming
  cases at the layer whose ports they exercise.

## Compatibility

No production module, port, adapter, persistence behavior, financial calculation, event contract,
API, OpenAPI schema, database structure, metric, runtime topology, or downstream contract changed.

## Documentation Decision

Repository context, critical-path/risk standards, and the codebase-review ledger changed because
test ownership and evidence paths changed. README, supported features, API inventory, OpenAPI, wiki
source, and platform context require no change.

## Validation

1. Focused position-history application suite passed: `9 passed`.
2. Complete transaction-processing unit package passed: `838 passed`.
3. Critical-path coverage and risk-based test coverage matrix guards passed.
4. Documentation/wiki and repository-wide Ruff lint/format gates passed.
5. Repository diff check passed.

## Remaining Work

Keep #719 open. Move the two remaining pure position policy tests into `domain/position` in a
separate slice; broader unified transaction-economics acceptance criteria remain outstanding.
