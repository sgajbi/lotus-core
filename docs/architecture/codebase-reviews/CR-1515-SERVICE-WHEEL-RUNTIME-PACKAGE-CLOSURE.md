# CR-1515: Service Wheel Runtime Package Closure

Date: 2026-07-11
Issue: #468 same-pattern production-readiness scan
Status: Implemented locally; image release validation pending

## Objective

Ensure every independently built service wheel contains the `app` package used by its container
entrypoint.

## Finding

Nine service projects configured setuptools with `where = ["app"]`. Their wheels installed orphan
top-level packages such as `consumers`, `logic`, and `repositories` but omitted `app.main`, root
modules, and the `app` namespace required by `python -m app.main`. Ingestion used root discovery but
did not explicitly constrain discovery to `app*`.

Repo-root tests and bind-mounted local Compose could mask this release-image defect.

## Implementation

- Standardized all service package discovery on `where = ["."]` and an explicit `app*` include.
- Added a repository-wide contract test that scans every service project with an `app` package and
  rejects discovery that cannot include the runtime namespace.
- Built all 12 service wheels and inspected each archive for `app/main.py`.

## Compatibility

No Python import used by the source tree, service entrypoint, API, event, database schema, image
metadata, or downstream contract changed. Wheels now contain the namespace the Dockerfiles already
declare as their entrypoint. The removed orphan top-level package layout was unsupported and could
not execute the documented runtime.

## Validation

- Wheel package contract: `1 passed`.
- Built wheel count: `12`; wheels missing `app/main.py`: `0`.
- Ruff, formatting, and diff checks passed.
- Reconciliation onto the post-PR-727 mainline reran the package contract successfully; complete
  wheel and image closure will run again in the aggregate release gates.

## Documentation Decision

Repository context and the review ledger change because this is a reusable build invariant. README
and wiki do not change: no developer command, operator procedure, API, or supported capability was
added. Image build/import proof remains required before PR merge.
