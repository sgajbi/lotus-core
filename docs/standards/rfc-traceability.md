# RFC Traceability Map

This document provides explicit implementation evidence pointers for RFCs that
remain active but are not fully closed.

## RFC-0005 - Enhance Unit Test Robustness and Code Quality

- Unit test robustness and quality hardening evidence:
  - `tests/integration/services/query_service/test_capabilities_router_dependency.py`
  - `tests/unit/services/query_service/test_capabilities_service.py`
  - `tests/unit/libs/portfolio-common/test_outbox_dispatcher.py`

## RFC-0019 - Standardize Epoch Fencing for Consumers

- Epoch fencing and reprocessing consumer evidence:
  - `src/libs/portfolio-common/portfolio_common/reprocessing.py`
  - `src/services/timeseries_generator_service/app/consumers/position_timeseries_consumer.py`
  - `tests/e2e/E2E_TEST_PLAN.md`

## RFC-0030 - CI Coverage Gate and lotus-manage Pipeline Parity Phase 2

- Coverage gate and CI parity evidence:
  - `.github/workflows/pr-merge-gate.yml`
  - `.github/workflows/main-releasability.yml`
  - `Makefile`
  - `pyproject.toml`
