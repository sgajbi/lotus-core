# CR-1563 Transaction Lifecycle Capability Catalog

Date: 2026-07-14

## Objective

Fix issue #757 by publishing implementation-backed product, transaction, corporate-action, and
lifecycle support truth for client, support, product, and engineering use.

## Findings

- Broad supported-feature documentation did not enumerate transaction and product lifecycle truth.
- A production-bookable generic `BUY`, `SELL`, `INTEREST`, or `DIVIDEND` path could be mistaken for
  complete product-specific lifecycle support.
- Eleven redemption/conversion codes were correctly production-disabled but not visible from a
  client/support capability matrix.
- Structured-product payoff and private-market commitment lifecycles had no focused issues.

## Change

- Created issue #757 for the governed catalog and issues #758/#759 for the newly confirmed
  structured-product and private-market gaps.
- Added a generated machine catalog for all 54 canonical transaction codes and 18 product lifecycle
  rows.
- Added a generator and blocking architecture guard for registry parity, uniqueness, issue-owned
  gaps, evidence paths, and documentation anchors.
- Added deep documentation and a client/support wiki page, then linked them from README, docs,
  supported-feature, Home, and sidebar navigation.

## Measurable Posture

The current registry snapshot contains 35 supported, 2 limited, 3 default-strategy, 2
internal-generated, 1 migration-only, and 11 target-not-implemented transaction types.

## Compatibility

No booking, calculation, API, event, database, topic, source-data product, or runtime topology
behavior changed. The slice makes existing support and limitation truth discoverable and guarded.

## Validation

- Five focused guard tests cover exact registry parity, drift, duplicates/missing codes, issue
  ownership, and documentation anchors.
- Transaction catalog, supported-features, front-door sync, architecture docs catalog, Ruff, and
  four changed-page wiki quality audits pass.

## Follow-Up

Issues #448, #450, #477-#481, #719, #754, #758, and #759 remain visible limitations. The cost-domain
duplicate transaction enum and repeated query position-effect selectors were removed under
CR-1564.
