# CR-1618: Coroutine-Preserving Repository Timing

## Objective

Expose one precise, reusable repository-timing contract to every Core capability without duplicating wrappers or weakening async repository ports.

## Finding

`portfolio_common.utils.async_timed` was used by nine repositories across transaction processing, query, valuation, timeseries, and portfolio aggregation. Its implementation and runtime tests were shared appropriately, but service checks skipped the common package and treated the decorator as untyped. The initial generic annotation also returned broad `Awaitable` callables, which erased the concrete coroutine signature required by structural async repository ports.

## Change

- Pointed MyPy at the worktree-local common library and enabled import following only for the deliberately typed instrumentation module.
- Changed `async_timed` to preserve `Callable[ParamSpec, Coroutine[Any, Any, ResultT]]` exactly.
- Added cancellation coverage proving latency observation executes while `CancelledError` propagates unchanged.
- Recorded the durable common-ownership and async-decorator rules in repository engineering context.

## Same-Pattern Review

All nine `async_timed` service consumers were checked together and now have no `untyped-decorator` findings. Other common `Awaitable` annotations are callback contracts rather than signature-preserving decorators, so they remain correctly broad.

## Measurable Improvement

- Unified transaction-processing strict debt reduced from 20 errors in 7 files to 8 errors in 4 files.
- Twelve decorator findings were removed and three latent cost/position async-port conformance failures were resolved by the precise coroutine contract.
- One shared implementation continues to serve five capabilities; no service-local compatibility wrapper was added.

## Validation

- `python -m mypy --strict --no-incremental src/services/portfolio_transaction_processing_service/app`
- Strict MyPy scan across all nine `async_timed` consumer files: no `untyped-decorator` findings.
- `python -m mypy --strict --no-incremental src/libs/portfolio-common/portfolio_common/utils.py`
- `python -m pytest -q tests/unit/libs/portfolio-common/test_utils.py`
- Focused Ruff and repository documentation guards.
- `git diff --check`

## Compatibility And Documentation Decision

Metric name, labels, timing behavior, exception propagation, decorator call sites, and repository APIs are unchanged. Cancellation observation is now explicitly protected. Repository engineering context changed because shared-code ownership and typing guidance changed; README and wiki capability truth did not change.

## Follow-Up

Continue #779 with explicit application/domain package exports, typed Kafka consumer boundaries, and the full-package strict gate. Broader `portfolio_common` extraction remains governed by evidence: shared placement requires demonstrated multi-capability ownership.
