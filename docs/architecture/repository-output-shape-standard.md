# Repository Output-Shape Standard

Date: 2026-07-01

## Purpose

Repository adapters are infrastructure boundaries. They may use SQLAlchemy ORM rows, SQL result
mappings, raw tuples, and database-specific joins internally, but application services,
source-data mappers, domain policies, and API assembly should receive explicit records or domain
objects whose shape is owned by the application boundary.

This standard closes the recurring defect behind GitHub issue #648 and the typed read-record fixes
in CR-1257 and CR-1258.

## Required Pattern

Use these output shapes:

| Repository evidence shape | Required boundary treatment |
| --- | --- |
| SQLAlchemy ORM row used only inside the repository or persistence unit of work | Allowed when it does not cross into application/source-data/domain logic. |
| SQLAlchemy ORM row returned to application/source-data/domain logic | Transitional only. Prefer a typed read/domain record. Must be registered in `repository-output-shape-guard` until converted. |
| Raw SQL tuple or SQLAlchemy row mapping | Convert at the repository boundary to a named record, value object, or explicit primitive tuple with documented field semantics. |
| Source-data product row evidence | Use a typed read record in `query_service.app.read_models` or a product-specific read-record module before DTO assembly. |
| API DTO, transport DTO, or downstream response model | Do not return these from repositories. Map them outside the infrastructure adapter. |

## Current Typed Precedents

- `PortfolioTaxLotWindow:v1` uses `PortfolioTaxLotReadRecord`.
- `PerformanceComponentEconomics:v1` uses `PerformanceEconomicsTransactionReadRecord`,
  `PerformanceEconomicsCashflowReadRecord`, and `PerformanceEconomicsCostReadRecord`.

These are the preferred shape for new high-value source-data paths.

## Guard

`make repository-output-shape-guard` runs `scripts/repository_output_shape_guard.py`.

The guard:

1. scans public repository methods under `src/services`,
2. detects return annotations that expose SQLAlchemy ORM classes imported from
   `portfolio_common.database_models`,
3. fails when a new ORM-returning method is not listed in the transitional exception register,
4. fails when a transitional exception becomes stale after a method is converted.

The guard is included in `make lint`, so it runs in the fast static lane.

## Transitional Exceptions

The current repository still has broad legacy ORM-returning surfaces across calculators,
persistence, operations, reference data, reporting, simulation, and query read paths. They are not
being silently declared clean.

The exact method-level transitional exception register lives in
`scripts/repository_output_shape_guard.py` as
`TRANSITIONAL_ORM_RETURN_EXCEPTIONS`. Future slices should remove entries as repository outputs are
converted to explicit records. Adding a new exception is allowed only when the slice documents why
immediate mapping is too large and records a follow-up.

## No Runtime Split Decision

This is a design-boundary and CI-enforcement improvement inside the existing `lotus-core`
deployable. It does not introduce a new runtime service.

## Validation

Focused tests:

- `tests/unit/scripts/test_repository_output_shape_guard.py`

Repository-native commands:

- `make repository-output-shape-guard`
- `make lint`
