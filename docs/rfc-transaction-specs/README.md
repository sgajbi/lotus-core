# Transaction Processing RFCs

This document set defines the canonical transaction-processing requirements for lotus-core.

It is structured so that:

* **shared documents** define reusable platform-wide standards
* **transaction RFCs** define transaction-specific behavior such as `BUY`, `SELL`, `DIVIDEND`, and `INTEREST`
* **templates** provide a standard authoring structure for future RFCs

This approach avoids repeating the same base rules in every transaction RFC and keeps each transaction document focused on business semantics, calculations, and behavior specific to that transaction type.

## How to use this documentation

### Shared documents

The `shared/` documents define common standards that apply across all transaction types, including:

* document governance
* glossary and canonical terminology
* normative rules and precedence
* common processing lifecycle
* common validation and failure semantics
* common calculation conventions
* accounting, cash, and linkage rules
* timing semantics
* idempotency and replay rules
* query, audit, and observability standards
* test strategy and gap assessment
* canonical modeling guidelines

These documents should be treated as foundational requirements and referenced by each transaction RFC.

### Transaction RFCs

The `transactions/` folder contains one RFC per transaction type.

Each transaction RFC must:

* reference applicable shared documents
* define transaction-specific business meaning
* define transaction-specific calculations
* define transaction-specific invariants
* define required data model additions or overrides
* define transaction-specific examples and tests

Example:

* `transactions/BUY/RFC-BUY-01.md`

### Templates

The `templates/` folder contains reusable templates for creating new transaction RFCs in a consistent format.

This ensures that all future transaction types follow the same documentation pattern.

## Document index

### Shared standards

* `shared/01-document-governance.md`
* `shared/02-glossary.md`
* `shared/03-normative-rules-and-precedence.md`
* `shared/04-common-processing-lifecycle.md`
* `shared/05-common-validation-and-failure-semantics.md`
* `shared/06-common-calculation-conventions.md`
* `shared/07-accounting-cash-and-linkage.md`
* `shared/08-timing-semantics.md`
* `shared/09-idempotency-replay-and-reprocessing.md`
* `shared/10-query-audit-and-observability.md`
* `shared/11-test-strategy-and-gap-assessment.md`
* `shared/12-canonical-modeling-guidelines.md`
* `shared/13-dual-leg-accounting-and-cash-adjustment-model.md`

### Transaction RFCs

* `transactions/BUY/RFC-BUY-01.md`
* `transactions/SELL/RFC-SELL-01.md`
* `transactions/DIVIDEND/RFC-DIVIDEND-01.md`
* `transactions/INTEREST/RFC-INTEREST-01.md`
* `transactions/CHARGE/RFC-CHARGE-01.md`
* `transactions/TRANSFER_IN_OUT/RFC-TRANSFER-01.md`
* `transactions/CASH MOVEMENT/RFC-CASH-MOVEMENT-01.md`
* `transactions/RFC-POSITION-DUAL-LEG-ALIGNMENT-01.md`

### Templates

* `templates/RFC-TRANSACTION-TYPE-TEMPLATE.md`

## Authoring rules

When adding or updating a transaction RFC:

1. Reuse shared standards instead of duplicating them.
2. Only define behavior specific to that transaction type in the transaction RFC.
3. If a rule becomes reusable across multiple transaction types, move it into `shared/`.
4. Keep formulas, invariants, and examples explicit.
5. Treat this documentation as the source of truth for implementation, testing, support, and audit.

## Intended audience

These documents are written for:

* engineers
* AI-assisted coding workflows
* QA and test automation
* business analysts
* support and operations teams
* audit and reconciliation stakeholders

## Long-term goal

This documentation set is intended to become the canonical transaction-processing specification for lotus-core, with one RFC per transaction type and a stable shared foundation reused across all transaction flows.
