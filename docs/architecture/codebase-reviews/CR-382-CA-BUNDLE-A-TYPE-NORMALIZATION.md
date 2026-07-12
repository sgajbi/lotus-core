# CR-382: CA Bundle A Type Normalization

Date: 2026-05-28

## Scope

Shared CA Bundle A transaction-type classification, validation, reconciliation, and deterministic
dependency ordering.

## Finding

CA Bundle A helpers uppercased transaction types without trimming source values. Padded lower-case
values such as ` spin_off `, ` spin_in `, or ` cash_consideration ` could:

1. miss the governed CA Bundle A transaction-type set,
2. return invalid transaction-type validation issues for otherwise valid corporate-action legs,
3. undercount source, target, or cash-consideration legs during basis reconciliation,
4. assign the wrong deterministic dependency rank during multi-leg processing.

This mattered because CA Bundle A flows carry corporate-action reconstruction and basis-transfer
semantics used by calculator consumers.

## Change

Added a shared CA Bundle A transaction-type normalizer and reused it across validation,
reconciliation, and dependency ordering. Added direct tests proving padded lower-case transaction
types are classified, validated, reconciled, dependency-checked, and ranked correctly while unknown
types remain outside the governed set.

## Evidence

Commands:

1. `python -m pytest tests/unit/libs/portfolio_common/test_ca_bundle_a_validation.py tests/unit/libs/portfolio_common/test_ca_bundle_a_reconciliation.py tests/unit/libs/portfolio_common/test_ca_bundle_a_ordering.py -q`
2. `python -m pytest tests/unit/libs/portfolio_common -q`
3. `python -m ruff check src/libs/portfolio-common/portfolio_common/ca_bundle_a_constants.py src/libs/portfolio-common/portfolio_common/ca_bundle_a_ordering.py src/libs/portfolio-common/portfolio_common/transaction_domain/ca_bundle_a_validation.py src/libs/portfolio-common/portfolio_common/transaction_domain/ca_bundle_a_reconciliation.py tests/unit/libs/portfolio_common/test_ca_bundle_a_validation.py tests/unit/libs/portfolio_common/test_ca_bundle_a_reconciliation.py tests/unit/libs/portfolio_common/test_ca_bundle_a_ordering.py`

## Closure

Status: Hardened.

No API, OpenAPI, wiki source, or platform contract change was required. This is a shared
transaction-domain corporate-action reliability hardening slice for deterministic CA Bundle A
processing.
