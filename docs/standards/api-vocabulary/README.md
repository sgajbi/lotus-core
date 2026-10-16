# lotus-core API Vocabulary Inventory

This folder stores the generated RFC-0067 API vocabulary inventory for `lotus-core`.

## Source coverage

The generator consumes `scripts/quality/openapi_quality_gate.py::service_schemas`, the same
supported HTTP application authority used by the API route catalog. It inventories operational
reads, the query control plane, write ingress, replay, reconciliation, and worker web surfaces.
Adding a supported HTTP app to that authority includes its actual OpenAPI operations without a
second service registry.

`serviceGroup` keeps the established `query` and `ingestion` identities. Other applications use
their complete authority key, such as `query_control_plane_service` and `event_replay_service`.
Operation identity is scoped by service group, HTTP method, and path: separate apps may each own
`GET /health/live` without collapsing their records or creating false duplicate errors.
Existing query/ingestion operations precede the added applications so the catalog keeps its
established first-source description/example precedence. Observed types and locations still
aggregate evidence from every included application.

## Domain-qualified business terms

RFC-0067 permits domain-qualified API attributes when the qualifier describes the business
relationship or process. App-owned DTOs and OpenAPI define those attributes; the platform's
primary-identifier registry does not enumerate every API field. The
[current Core ownership decision](https://github.com/sgajbi/lotus-core/issues/531#issuecomment-6225029909)
classifies exactly two existing replay API terms:

| Term | Meaning and source contract |
|---|---|
| `ingestion_job_id` | Optional reference from `ConsumerDlqEventResponse` to the original durable ingestion-job owner. The failure fact keeps its own `event_id`; the job-scoped response keeps `job_id`. Missing legacy ownership remains null, and `correlation_id` is observability metadata rather than an ownership substitute. |
| `ingestion_outcome` | `IngestionEvidenceBundleResponse` source-batch disposition: `accepted`, `partially_accepted`, `rejected`, `quarantined`, or `empty`. It is distinct from execution status, replay or repair posture, completeness, readiness, and financial/source qualification. |

Both fields are served by `event_replay_service`: “ingestion” identifies the related business
process, not the implementation of the serving service. Their exact names retain
`lotus.ingestion_job_id` and `lotus.ingestion_outcome`; this classification adds no namespace,
primary identifier, or payload alias. Every other unapproved `ingestion_`, `query_`, `dto_`, and
`db_` name remains rejected, including near matches and suffix extensions. Catalog and endpoint
links reject rebinding either approved concept to another name or semantic ID.

The definitions live in `ingestion_job_replay_dto.py` and `ingestion_job_lifecycle_dto.py` under
`src/services/ingestion_service/app/DTOs/`. Actual OpenAPI links the first model through
`GET /ingestion/dlq/consumer-events` and the evidence bundle's `consumer_dlq_events`, and returns
the second model from `GET /ingestion/jobs/{job_id}/evidence`. Owning tests verify those links,
the nullable owner, all five disposition values, and rejected aliases and implementation names.

## Regenerate

Run from the `lotus-core` repository root using its configured environment:

```powershell
python scripts/development/repository_python.py scripts/quality/api_vocabulary_inventory.py `
  --output docs/standards/api-vocabulary/lotus-core-api-vocabulary.v1.json
```

```bash
python scripts/development/repository_python.py scripts/quality/api_vocabulary_inventory.py \
  --output docs/standards/api-vocabulary/lotus-core-api-vocabulary.v1.json
```

## Validate

```powershell
python scripts/development/repository_python.py scripts/quality/api_vocabulary_inventory.py --validate-only
```

The same command works in Bash. `make api-vocabulary-gate` additionally checks the route catalog.

Validation is non-mutating and fail-closed. It validates freshly generated and committed inventory
structure and compares service declarations and every operation identity directly with the complete
OpenAPI authority. Missing or unknown services and operations, duplicate operations within an app,
changed operation IDs, and stale service metadata fail before artifact publication. It then
requires semantic parity while ignoring only the volatile top-level `generatedAt`
timestamp. A stale description, type, example, route, control, or catalog entry fails with the first
different JSON path and the governed regeneration command.

Generation also preserves the existing canonical-name and semantic rules. A source contract that
violates those rules blocks output; inventory coverage must not be reduced to hide that failure.
Vocabulary validation proves source contract coverage, not running-stack behavior, financial
correctness, or production readiness.
