# CR-1658: Exact Financial Numeric Producer Boundaries

## Scope

This review is a bounded continuation of GitHub issue #829. It covers source-owned client-policy,
benchmark, index, risk-free, look-through, and instrument DTO fields whose persistence contract is
`NUMERIC(18,10)` or `NUMERIC(18,4)`. It does not claim closure of calculated-output precision.

## Finding

Twenty ingress fields enforced business ranges but did not enforce their declared persistence
precision and scale. PostgreSQL could therefore round excess scale or reject magnitude overflow
after synchronous validation had succeeded and asynchronous processing had begun.

## Resolution

- Reused the framework-neutral `BOUNDED_18_10_EXACT` and `BOUNDED_18_4_EXACT` domain policies
  through shared Pydantic annotated types.
- Applied exact validation to sustainability allocations, tax rates and thresholds, income needs,
  liquidity reserves, withdrawals, model-portfolio weights, benchmark composition and returns,
  index prices and returns, risk-free values, look-through weights, and FX-contract economics.
- Preserved existing allocation and rate ranges.
- Ordered range metadata before exact-value validation so generated OpenAPI retains standard
  `minimum`, `maximum`, and `exclusiveMinimum` keywords for SDK and form generators.
- Rejected JSON floating-point inputs before Pydantic can coerce them to a rounded `Decimal`.
  Exact financial numerics now advertise decimal strings and lossless integers as their accepted
  JSON input shapes while retaining machine-readable range bounds.
- Enforced positive instrument buy amount, sell amount, and contract rate at ingress, matching the
  existing persistence profile.
- Published each exact storage shape and reject-not-round behavior in generated OpenAPI.

No database schema, migration, event topic, or runtime-topology change is required. Valid values
that are exactly representable retain their prior value.

## Compatibility

Values supplied as JSON floating-point numbers, values with excess scale or magnitude overflow,
and nonpositive FX-contract economics now fail synchronously instead of failing or changing during
persistence. Callers must send fractional financial values as decimal strings. This is an
intentional correctness hardening. No blanket rounding was introduced.

## Evidence

- Signed client-policy commit `6657bef0f001dac024189f2579449588d9bee7cc`.
- Signed benchmark/reference/instrument commit
  `afed3e010643ea55e0cc20e5aa113bb7aa970000`.
- 149 focused tests passed with warnings treated as errors, including loss-prone JSON-number
  rejection and machine-readable JSON Schema range assertions for all 17 bounded fields.
- Type checking passed across 238 source files.
- OpenAPI quality, vocabulary parity, Spectral, Ruff, formatting, and diff-hygiene gates passed.

## Remaining #829 work

Owner-specific review remains for simulation and reconciliation commands, transaction events,
position-history accumulation, cashflow events, accrued-income offsets, and lineage-aware
calculated-output policies. Those paths must reject impossible source facts while leaving any
rounding policy under the producing domain's explicit, versioned ownership.

## Documentation decision

The repository review ledger and generated OpenAPI are the durable truth changed by this slice.
No operator flow, business methodology, or wiki-authored behavior changed, so no wiki source update
is required.
