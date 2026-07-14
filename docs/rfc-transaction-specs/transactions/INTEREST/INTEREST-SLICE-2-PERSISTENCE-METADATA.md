# INTEREST Slice 2 - Metadata Enrichment and Persistence Traceability

## Scope

Slice 2 establishes deterministic metadata enrichment for INTEREST and verifies metadata persistence and propagation through processing paths.

## Delivered Artifacts

- `src/services/portfolio_transaction_processing_service/app/domain/transaction/booking_metadata.py`
- `src/services/portfolio_transaction_processing_service/app/domain/transaction/__init__.py` (exports)
- `src/services/portfolio_transaction_processing_service/app/application/cost_basis_processing/execution.py` (INTEREST enrichment integration)
- `tests/unit/services/portfolio_transaction_processing_service/domain/transaction/test_booking_metadata.py`
- `tests/unit/services/portfolio_transaction_processing_service/application/cost_basis_processing/test_execution.py` (INTEREST processing integration test)
- `tests/integration/services/persistence_service/repositories/test_repositories.py` (INTEREST metadata UPSERT persistence test)

## Behavior

`enrich_booking_metadata` now enforces deterministic defaults for INTEREST:

- `economic_event_id` default: `EVT-INTEREST-{portfolio_id}-{transaction_id}`
- `linked_transaction_group_id` default: `LTG-INTEREST-{portfolio_id}-{transaction_id}`
- `calculation_policy_id` default: `INTEREST_DEFAULT_POLICY`
- `calculation_policy_version` default: `1.0.0`
- `cash_entry_mode` normalization via the service-owned settlement policy (`AUTO_GENERATE` default)

Upstream-provided values are preserved unchanged.

## Persistence and Propagation Evidence

- The unified cost workflow enriches INTEREST before engine processing and outbox emission.
- Unit test verifies enriched metadata is present in the persisted/updated transaction object and outbound payload.
- Integration repository test verifies INTEREST linkage/policy/source/cash-entry metadata persists and updates correctly on UPSERT.

## Shared-Doc Conformance Note (Slice 2)

Validated shared standards for this slice:

- `shared/04-common-processing-lifecycle.md`: metadata enrichment step is deterministic in processing flow.
- `shared/07-accounting-cash-and-linkage.md`: linkage identifiers and cash-entry mode behavior are explicit and traceable.
- `shared/09-idempotency-replay-and-reprocessing.md`: stable metadata defaults support replay-safe linkage.
- `shared/10-query-audit-and-observability.md`: enriched metadata is propagated into downstream payloads for auditability.
- `shared/11-test-strategy-and-gap-assessment.md`: unit + integration coverage added for end-to-end metadata persistence.

## Residual Gaps (Expected for Later Slices)

- INTEREST calculation invariants and direction semantics are Slice 3.
- cash-entry mode execution behavior and withholding reconciliation are Slice 4.
- query/observability contract extensions are Slice 5.

