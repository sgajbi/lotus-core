# CR-1635: Money Amount Rounding Convergence

## Objective

Remove the shared monetary value object's ungoverned `ROUND_HALF_UP` exception and align its explicit
boundary operation with RFC-0063 and repository rounding policy version `1.1.0`.

## Finding

`MoneyAmount.quantized()` was the only production definition using `ROUND_HALF_UP`; Query and QCP
precision policies already use `ROUND_HALF_EVEN`. Repository-wide call-site inventory found no
production invocation of `quantized()`: Query reporting-currency and FX paths use `MoneyAmount` for
normalization/conversion but retain unrounded intermediates, and the only direct quantization call
was its unit test. The inconsistent midpoint behavior therefore created future reconciliation risk
without currently changing a persisted, API, or runtime result.

## Change

- Changed the explicit helper to `ROUND_HALF_EVEN` and exposed rounding policy version `1.1.0`.
- Added positive and negative midpoint, zero, large-value, multi-currency, and explicit-quantum
  golden vectors, including three-decimal currency proof without inventing a currency-minor-unit
  registry.
- Retained unrounded `MoneyAmount.converted()` behavior; quantization remains an explicit output
  boundary selected by the caller.

## Compatibility

Direct callers of `MoneyAmount.quantized()` now receive half-even tie behavior. The repository has
no production callers, so no API/OpenAPI, database, event, topic, persisted amount, Query/QCP output,
or downstream field changes in this slice. A future production caller must select the governed
quantum for its boundary; the default remains `0.01` and is not a claim about every currency's minor
unit.

## Validation

- 51 shared-money, Query rounding/precision, Query reporting-currency/FX, and QCP precision tests
  passed.
- Focused Ruff and strict MyPy passed; domain, monetary-float, architecture-documentation, wiki,
  RFC-ledger, supported-feature, incident-playbook, and diff guards passed.
- The platform cross-app validator failed before comparison because it loads Core's package-relative
  precision-policy module as a synthetic top-level file. The deduplicated automation defect and
  required regression proof are tracked by `sgajbi/lotus-platform#578`. Issue #761 must remain in
  progress until that governed cross-app evidence can run successfully.

## Documentation Decision

The existing rounding standard, repository context, review ledger, and issue #761 change. README,
API inventory, supported features, OpenAPI, migrations, operator runbooks, and wiki source do not
change because runtime/product truth is unchanged.
