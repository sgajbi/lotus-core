# Shared Requirement: Common Validation and Failure Semantics

## Validation Categories

Every transaction type must define validation across:

- required fields
- numeric ranges and signs
- enum values
- referential integrity
- reconciliation tolerance
- linkage integrity
- policy-required fields

## Standard Failure Outcomes

Each validation or processing failure must resolve to one of:

- `HARD_REJECT`
- `PARK_PENDING_REMEDIATION`
- `ACCEPT_WITH_WARNING`
- `RETRYABLE_FAILURE`
- `TERMINAL_FAILURE`

## Rule

A transaction RFC must define which failures are mapped to which outcome.

## Support Requirement

All failures must produce:

- failure code
- failure reason
- lifecycle stage
- correlation id
- economic event id where available

## Ordinary Settlement Rejections

Fee-equal or fee-dominated SELL, DIVIDEND, and INTEREST income settlement is a non-retryable
`HARD_REJECT`. The application opens the combined unit of work and classifies physical and semantic
idempotency first, so harmless historical duplicates remain acknowledgements. It must reject a
newly claimed or repair delivery before cost, position, cashflow, or commit; the uncommitted claim
rolls back with the unit of work. Defensive direct-adapter paths must preserve the same result.

Diagnostics expose only the stable family reason code, portfolio and transaction identity,
transaction type, failing field, available proceeds, resolved fee, and net settlement amount. They
must not expose raw payloads, exception text, credentials, or infrastructure details.

| Family | Stable reason code |
|---|---|
| SELL | `SELL_010_NON_POSITIVE_NET_SETTLEMENT` |
| DIVIDEND | `DIVIDEND_013_NON_POSITIVE_NET_SETTLEMENT` |
| INTEREST income | `INTEREST_017_NON_POSITIVE_NET_SETTLEMENT` |
