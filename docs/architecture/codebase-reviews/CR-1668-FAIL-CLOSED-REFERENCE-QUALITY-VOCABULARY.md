# CR-1668: Fail-Closed Reference Quality Vocabulary

## Finding

Reference coverage counted only recognized stale, blocking, and warning families. A complete date
window containing a blank or vendor-specific `quality_status` therefore had no issue count and could
be classified `COMPLETE` with `publication_gate=ALLOW`. Classification taxonomy repeated the same
family-specific counting, while DPM model targets could report unknown data quality but retain
`supportability.state=READY`.

## Resolution

`portfolio_common.market_reference_quality` now owns normalized, bounded status-family counting.
Recognized accepted, partial, stale, and blocking values retain their behavior. Every other value,
including blank and vendor-specific values, increments `unknown_count`. Coverage precedence remains
fail closed: blocking and stale evidence outrank unknown evidence, and unknown evidence outranks
partial or complete evidence.

Query Control Plane coverage emits `UNRECOGNIZED_QUALITY_STATUS` and blocks publication.
Benchmark coverage evaluates component-definition quality and timestamps alongside prices and
returns, so every contributing record participates in the publication decision. Classification
taxonomy consumes the same policy. DPM model targets evaluate both the governing model definition
and its targets and cannot be ready unless all contributing source quality is complete.

## Compatibility

This is a behavior correction for previously unrecognized source values. Existing response shapes,
recognized status behavior, persistence, migrations, OpenAPI schemas, Kafka contracts, and runtime
topology are unchanged.

## Validation

- shared market/reference classifier and normalization tests;
- benchmark and risk-free publication-gate regressions;
- benchmark-component quality and latest-evidence timestamp regressions;
- classification-taxonomy regression;
- DPM model-definition and target quality/readiness regressions;
- Ruff format and lint;
- repository-native contract, architecture, documentation, and wiki gates before merge.

Issue: #860.
