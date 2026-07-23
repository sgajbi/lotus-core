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

Retained-runtime repair then exposed a second deterministic defect: the same transaction IDs were
dated from the moving history-window start, including offsets up to 900 days. The 240-day CI profile
therefore generated future facts beyond its own as-of date, while market, FX, index, benchmark, and
reference-definition economics changed for the same natural key when the wall clock or history
depth changed. Positional market/FX batch numbers amplified that content churn.
The downstream verifier compounded the problem by issuing one exact-as-of position-history request
per expected security even though that product records transaction dates. The strategic
HoldingsAsOf response already carried the required as-of quantities and valuations.

## Decision

One source-backed decision owns the complete sample pack. Each immutable generated write segment
has a content-derived idempotency key and a source-owned completeness evaluator. Portfolio-bundle
completeness also requires the existing QCP analytics source product to prove the exact generated
business-calendar window and cardinality with no missing observation dates. First boot selects all
missing segments; a partial or evolved retained pack selects only the segments whose business facts
are absent or different; an unchanged retained restart ingests nothing and emits
`reason=unchanged_pack_present`. Explicit force refresh bypasses completeness reads and selects the
complete pack. This preserves existing APIs, schemas, seeded identities, first boot, and manual
refresh while removing implicit source replay and the unsafe portfolio-existence shortcut.
The generator now resolves RFC-0076's fixed canonical as-of date, uses a fixed economic anchor, and
derives every overlapping observation from its absolute date. Market and FX payloads are partitioned
by logical security or ordered currency pair instead of positional batch number, with chronological
rows and a versioned `lotus-demo-pack:v2` content namespace.
The anchor is the already-deployed v1 date (`2023-07-20`), not a newly derived window start. This
keeps existing transaction IDs and dates byte-compatible because ordinary source UPSERT correctly
rejects moving an accepted transaction ID to a different economic date.

## Same-pattern review

The scoped scan covered the Compose loader command, portfolio and terminal-position state,
instrument and transaction facts, market/FX batching, benchmark/index/risk-free posts, app-local
stack contract, operations guide, RFC-048, repository context references, and wiki operations
guidance. No second default force path was found. The earlier portfolio-existence compatibility
path and duplicate portfolio/reference ingestion wrappers were removed after every generated
segment gained an evaluator.

## Validation

- Focused demo-pack contracts: `39 passed` with warnings treated as errors; the combined demo-pack
  and front-office seed suite passes `108` tests with warnings treated as errors.
- Ruff lint and format: passed for all touched Python files.
- Strict MyPy: passed for `tools/demo_data_pack.py`; distinct reference-family evidence names
  prevent local annotation reuse from weakening the typing gate.
- Compose configuration rendering, architecture guard, and wiki/docs gates: passed.
- Retained-volume ingest-only restart exited `0` in 3.3 seconds and logged
  `reason=unchanged_pack_present`.
- The no-op kept `ingestion_jobs` at `217` and `portfolio_valuation_jobs` at `14,939`;
  aggregation/outbox counts advanced only while the inherited pre-fix backlog was processing.
- Remote Feature Lane `29680323658` passed workflow lint, lint/typecheck/contracts/security and
  warning gates, integration-lite, and unit-db at exact signed commit `c4f16143d348b3e3d6b0e7a2aa7c4e1cb505d302`.
- The stronger retained repair selected the exact incomplete/evolved segments and published them,
  then the bounded 900-second downstream verifier timed out on missing `CASH_USD` daily position
  history while current positions, valuations, and transaction counts were present. This is
  convergence evidence, not a no-op pass.
- The following exact-head ingest-only attempt failed closed with HTTP 409 before accepting a new
  job because transaction DTO normalization supplied a time-dependent default `created_at` that
  was absent from the raw content key. The failed attempt left `ingestion_jobs` at 468/max id 468.
  Generated transactions now carry their governed transaction timestamp as deterministic
  `created_at`; two independent DTO normalizations produce the same SHA-256 request fingerprint.
- Cross-window tests now prove identical transactions, no transactions beyond the fixed as-of, and
  identical overlapping market, FX, index-price, index-return, benchmark-return, and risk-free
  economics for 240-day and 1,095-day profiles. The full profile uses 32 logical requests and
  26,753 records, inside the app-local 500-request/50,000-record rate window.
- The full five-portfolio 1,095-day pack now owns a direct 500-request/50,000-record regression; the
  smaller 240-day single-portfolio partition test is no longer misreported as full-pack evidence.
- Business-calendar completeness requests the full bounded observation page, requires a terminal
  page, and compares every returned `valuation_date` with the exact ordered generated dates. A
  same-count substituted-date regression fails closed.
- The balanced-SGD terminal Sony holding was corrected from `-200` to `1,000`: its governed source
  stream buys `1,200` and later sells `200`. An executable cross-contract regression now reduces
  every generated portfolio/security stream through the canonical position reducer and requires
  all declared terminal holdings to match, preventing verifier expectations from masking incomplete
  derived state.
- The first targeted image build failed before writes because the persistence Dockerfile copied the
  demo tool but not its existing RFC-0076 contract-loader dependency. The Dockerfile now copies both
  files and a stack-contract regression protects that runtime packaging boundary.
- Terminal validation now makes one explicit as-of HoldingsAsOf request per portfolio and compares
  every expected security from that response. The focused regression proves two securities with two
  total reads (holdings plus transaction count), removing the per-security polling N+1 and the false
  exact-date history requirement.

The second-run zero-write/count/maturity proof remains pending after this runtime fix-forward and
must not be inferred from either diagnostic attempt.

## Documentation and compatibility

Existing operations, RFC, context, and wiki sources were corrected in place; no duplicate playbook
was added. No API, OpenAPI, event, database, migration, or production runtime contract changes are
needed because `demo_data_loader` is an app-local bootstrap utility.
