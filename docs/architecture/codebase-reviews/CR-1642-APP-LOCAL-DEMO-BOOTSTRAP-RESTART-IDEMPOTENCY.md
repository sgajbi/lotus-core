# CR-1642: App-Local Demo Bootstrap Restart Idempotency

## Scope

- GitHub issue: #811
- Runtime: `lotus-core-app-local` retained-volume restart
- Owners: `docker-compose.yml` and `tools/demo_data_pack.py`

## Finding

After the 2026-07-19 Windows host restart, the shared Core project was restored without deleting
its PostgreSQL volume. The existing data had already produced complete/current canonical state, but
the default one-shot loader replayed 103 market-price batches and 80 FX-rate batches. The replay
created 8,194 pending and 663 processing valuation jobs and temporarily made the canonical
portfolio stale.

This was deterministic implementation behavior rather than a Docker or database failure:

1. Compose unconditionally supplied `--force-ingest`.
2. Reference ingestion ran after the portfolio-existence branch, including when that branch logged
   an ingestion skip.
3. The operator guide described the pack as ingested only when not already present.

## Decision

One decision owns the complete sample pack. First boot ingests portfolio and reference data;
explicit force refresh ingests both; an unchanged retained restart ingests neither and emits
`reason=unchanged_pack_present`. This preserves existing APIs, schemas, seeded identities, first
boot, and manual refresh while removing implicit source replay.

## Same-pattern review

The scoped scan covered the Compose loader command, portfolio-existence check, market/FX batching,
benchmark/index/risk-free posts, app-local stack contract, operations guide, RFC-048, repository
context references, and wiki operations guidance. No second default force path was found.

## Validation

- Focused demo-pack and Compose contracts: `24 passed`.
- Ruff lint and format: passed for all touched Python files.
- Strict MyPy: passed for `tools/demo_data_pack.py`.
- Compose configuration rendering, architecture guard, and wiki/docs gates: passed.
- Retained-volume ingest-only restart exited `0` in 3.3 seconds and logged
  `reason=unchanged_pack_present`.
- The no-op kept `ingestion_jobs` at `217` and `portfolio_valuation_jobs` at `14,939`;
  aggregation/outbox counts advanced only while the inherited pre-fix backlog was processing.
- Remote Feature Lane `29680323658` passed workflow lint, lint/typecheck/contracts/security and
  warning gates, integration-lite, and unit-db at exact signed commit `c4f16143d348b3e3d6b0e7a2aa7c4e1cb505d302`.

Normal-mode verification and canonical maturity proof remain pending until that pre-fix backlog
converges.

## Documentation and compatibility

Existing operations, RFC, and wiki sources were corrected in place; no duplicate playbook was
added. No API, OpenAPI, event, database, migration, or production runtime contract changes are
needed because `demo_data_loader` is an app-local bootstrap utility.
