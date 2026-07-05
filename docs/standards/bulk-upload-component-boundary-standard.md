# Bulk Upload Component Boundary Standard

Bulk upload handling is split into parser/validator, commit orchestration, and publisher adapter
responsibilities.

## Responsibilities

`upload_validation.py` owns:

1. file-format detection,
2. CSV and XLSX parsing,
3. parser budget enforcement for max rows, max columns, and max cell length,
4. streamed XLSX row iteration without materializing the whole worksheet,
5. header normalization,
6. row-value normalization,
7. entity DTO validation,
8. validation report construction.

`upload_ingestion_service.py` owns:

1. preview result assembly,
2. commit policy for empty uploads, invalid rows, partial commit allowance, and no-valid-row
   rejection,
3. application result construction.

`upload_record_publisher.py` owns the publisher port, and `upload_publishers.py` owns the
`IngestionService` adapter that dispatches validated records to existing canonical ingestion
publish methods.

## Boundary Rules

The validator must not import FastAPI, Kafka, database sessions, or `IngestionService`.

The validator must not parse unbounded uploads. It owns row, column, and cell-length budgets for
CSV and XLSX inputs. HTTP byte limits and rate limits are necessary outer controls but do not
replace parser-level budgets.

The upload orchestration service must not parse CSV/XLSX files inline, import `IngestionService`,
or own entity-specific publish methods. It depends on `BulkUploadValidator` and
`UploadRecordPublisher`.

## Enforcement

`make architecture-guard` runs `scripts/upload_component_boundary_guard.py`. The guard proves the
split components exist and blocks the representative monolithic patterns from returning.

## Compatibility

This is a design-time modularity rule inside the existing ingestion deployable. It does not change
upload route paths, request forms, response DTOs, OpenAPI metadata, Kafka topics, payload mapping,
or runtime topology.
