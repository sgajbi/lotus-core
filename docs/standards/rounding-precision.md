# Rounding and Precision Standard

This repository adopts the platform-wide mandatory standard defined in `lotus-platform/Financial Rounding and Precision Standard.md` and RFC-0063.

## Local Enforcement

- Monetary/financial calculations use `Decimal`.
- Intermediate calculations do not round.
- Output boundaries apply canonical scale + `ROUND_HALF_EVEN` via `precision_policy` helpers.
- Shared `MoneyAmount.quantized()` uses `ROUND_HALF_EVEN` and declares policy version `1.1.0`.
  It is an explicit boundary operation: conversion and other intermediates remain unrounded, and
  callers must supply the governed quantum when the boundary is not the default `0.01`.
- Runtime policy metadata is exposed as `ROUNDING_POLICY_VERSION = "1.1.0"`.
- Compatibility policy_version for this repository is `1.1.0`.
- API/import normalization should call `normalize_input(value, semantic_type)` before domain execution.
- Any change to rules requires RFC approval in PPD.

## Enforcement Points

- Boundary validation: `precision_policy.py` (`normalize_input`) rejects malformed and over-scale inputs.
- Output boundary quantization: `quantize_*` helpers apply final rounding for response shaping.
- Query-service boundary helpers include explicit `performance` and `risk` semantics in addition
  to the legacy generic `ratio` helper so platform golden-vector validation can compare the same
  named financial semantics across core, performance, risk, manage, report, and gateway services.
- Intermediate precision preservation: domain logic keeps unquantized `Decimal` until output-edge serialization.

## Calculated-Output Lineage

- Owner-specific calculated outputs use the versioned policies inventoried in
  `financial-calculated-output-policies.v1.json`; a storage type alone is not a calculation policy.
- A lineage-bound calculation records its algorithm/version, working precision, complete numeric
  output-policy identity, and deterministic hashes of the financial inputs, calculation, and
  normalized output.
- Canonical cashflow calculation executes `cashflow-ledger-output@1.0.0` and persists that lineage
  with each newly materialized cashflow row. The policy uses 64-digit intermediate precision and
  one final `NUMERIC(18,10)` half-even normalization.
- The cashflow lineage column is nullable for compatibility with rows created before migration
  `c130b2c3d503`. Null legacy lineage is an explicit absence of evidence; consumers must not infer
  a policy version or synthesize hashes from the stored amount.
- Changes to a policy version, source-input identity, calculation method, or normalized output must
  change the corresponding lineage identity. Identical inputs and policy must remain deterministic.

## Monetary Float Guard

- CI runs python scripts/quality/check_monetary_float_usage.py.
- Baseline allowlist: docs/standards/monetary-float-allowlist.json.
- The current baseline is zero active findings and an empty allowlist; stale allowlist entries fail
  the guard.
- New findings fail CI until explicitly approved and allowlisted in dedicated PR.
- Each allowlist entry requires `justification`, `owner`, and `review_by` metadata.
- Stale allowlist entries (past `review_by`) fail CI.

## Deviation and Change Control

- Deviations require RFC/ADR approval linked from repository docs and the platform standard (RFC-0063).
- Compatibility-breaking policy changes require explicit RFC migration notes.

## Cross-Service Regression Link

- Shared golden fixture: `tests/fixtures/rounding-golden-vectors.json`.
- Platform check: `lotus-platform/automation/Validate-Rounding-Consistency.ps1`.
- Automation guide: `lotus-platform/automation/docs/Automation-Guide.md`.
- Evidence artifact: `Rounding Consistency Report`.

## Shared Money Consumer Inventory

- Query reporting-currency mapping uses `MoneyAmount` for currency-safe normalization but delegates
  conversion and does not call `quantized()`.
- Query cached FX conversion uses `MoneyAmount.converted()` and preserves the unrounded Decimal.
- No other production path calls `MoneyAmount.quantized()` as of 2026-07-18; repository search and
  focused tests are the compatibility proof for issue #761.

