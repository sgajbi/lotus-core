# CR-1620: Typed Kafka Consumer Boundary

## Objective

Make transaction-processing Kafka delivery strict-checkable without duplicating the shared runtime or hiding constructor dependencies behind variadic forwarding.

## Finding

`portfolio_common.kafka_consumer.BaseConsumer` was treated as `Any` because the large legacy shared module was skipped by MyPy. Both transaction consumers also accepted untyped `*args` and `**kwargs`, so delivery configuration and use-case injection were invisible to static checks. The transaction consumer covered malformed JSON but not a missing Kafka payload.

## Change

- Annotated the shared base constructor, abstract message boundary, run loop, and shutdown entry point.
- Followed the shared consumer module silently as an explicit migration boundary instead of claiming the whole legacy implementation is strict-clean.
- Replaced variadic constructors in both transaction consumers with explicit Kafka configuration, execution profile, and use-case dependencies.
- Extended transaction delivery coverage to reject missing payload bytes before application dispatch.
- Recorded the explicit consumer-constructor rule in repository engineering context.

## Same-Pattern Review

All 11 Core `BaseConsumer` subclasses were scanned. None now inherit from an `Any` base. Capability-specific untyped methods remain in valuation, timeseries, and aggregation consumers and are recorded against consolidation issues #713 and #714 rather than mixed into #779.

## Measurable Improvement

- Unified transaction-processing strict debt reduced from 4 errors in 2 files to zero errors across 179 source files.
- Two opaque constructors became explicit and statically validated.
- Missing and malformed Kafka payloads are both proven to stop before use-case invocation.

## Validation

- `python -m mypy --strict --no-incremental src/services/portfolio_transaction_processing_service/app`
- Strict inheritance scan across all 11 Core `BaseConsumer` subclasses.
- `python -m pytest -q tests/unit/services/portfolio_transaction_processing_service/delivery/kafka/test_transaction_consumer.py tests/unit/services/portfolio_transaction_processing_service/delivery/kafka/test_replay_request_consumer.py`
- Focused Ruff and repository documentation guards.
- `git diff --check`

## Compatibility And Documentation Decision

Kafka topics, groups, retry/DLQ behavior, correlation lineage, execution profiles, use-case calls, and public constructor parameter names/defaults are preserved. The missing-payload rejection is an intentional validation proof of existing behavior. Repository context changed; README and wiki capability truth did not.

## Follow-Up

Add the exact full-package strict command to the governed test lane, run batch-wide validation, and then move #779 to fixed-local review readiness.
