# RFC-0083 Ingestion Source-Lineage Target Model

This document is the RFC-0083 Slice 4 target model for ingestion evidence, source lineage, partial
rejection, replay, DLQ, and repair supportability in `lotus-core`.

It does not change runtime behavior, persistence, DTOs, OpenAPI output, or downstream contracts. It
defines the target evidence model that later ingestion and replay runtime slices must use.

## Target Principle

Every accepted, partially accepted, rejected, quarantined, replayed, or repaired source payload must
be traceable through a stable evidence model.

Operators and downstream consumers must not need database inspection, logs, or private route-specific
conventions to answer:

1. which source batch produced a record,
2. which validation report accepted, rejected, or quarantined records,
3. whether partial success occurred,
4. whether replay changed publish state or only validation state,
5. whether DLQ repair is blocked, safe to retry, already replayed, or needs human action.

## Current Implementation Baseline

Current useful building blocks:

1. `ingestion_service` owns canonical write ingress for transactions, portfolios, instruments, market
   prices, FX rates, business dates, benchmark/reference data, upload preview/commit, and transaction
   reprocessing requests.
2. `event_replay_service` owns ingestion job diagnostics, backlog and health views, replay, DLQ
   listing, replay audit, idempotency diagnostics, and operations control.
3. `ingestion_jobs` and `ingestion_job_failures` provide durable job and failure bookkeeping.
4. `consumer_dlq_events` and `consumer_dlq_replay_audit` provide durable consumer-side failure and
   replay evidence.
5. important routes already carry `idempotency_key`, `correlation_id`, `trace_id`, `source_system`,
   `source_batch`, and record-level failure evidence in several places.
6. replay fingerprints already prevent duplicate successful replay for equivalent payloads.

Current gaps:

1. there is no named `IngestionEvidenceBundle` product,
2. accepted/rejected/quarantined/partially accepted states are not one governed vocabulary across all
   ingress surfaces,
3. validation report identity is not consistently tied to source batch identity,
4. replay and DLQ evidence is operationally rich but not yet packaged as a reusable evidence contract,
5. retention and archival posture is not yet explicit for raw source records, validation reports, or
   repair evidence.

## Source Batch Identity

The target source batch identity scope is:

| Field | Meaning |
| --- | --- |
| `tenant_id` | Tenant or operating scope for the ingest |
| `source_system` | Upstream system or adapter that supplied the payload |
| `source_batch_id` | Upstream or adapter batch identifier |
| `payload_kind` | Domain payload family, for example `transactions`, `market_prices`, or `fx_rates` |
| `feed_name` | Optional upstream feed or file family |
| `observed_at` | When the upstream source emitted or observed the data |
| `ingested_at` | When Lotus accepted the payload into ingestion |
| `idempotency_key` | Request or replay idempotency key |
| `correlation_id` | Cross-service correlation id |
| `source_record_keys` | Stable record identifiers in the batch when available |

The executable helper is:

1. `src/libs/portfolio-common/portfolio_common/ingestion_evidence.py`
2. `tests/unit/libs/portfolio-common/test_ingestion_evidence.py`

The helper creates a deterministic source-batch fingerprint from a canonical JSON payload and SHA-256
digest. Record-key ordering and duplicate record keys do not change the fingerprint.

The source-batch fingerprint intentionally excludes `ingested_at`, `idempotency_key`, and
`correlation_id`. Those fields describe an ingestion or replay attempt, not the upstream source batch.
Validation reports and replay evidence must still carry them separately.

## Validation Report Contract

Target validation reports must include:

1. `validation_report_id`,
2. source batch fingerprint,
3. product or payload kind,
4. validation profile and version,
5. accepted, rejected, quarantined, warning, and skipped counts,
6. record-level findings with stable source record keys,
7. failure code, severity, field path, and human-readable message,
8. whether the payload is replayable,
9. whether partial success was allowed,
10. retention class and archival deadline.

Validation report status vocabulary:

| Status | Meaning |
| --- | --- |
| `accepted` | All submitted records were accepted for downstream processing |
| `partially_accepted` | At least one record was accepted and at least one was rejected or quarantined |
| `rejected` | No records were accepted; at least one record failed validation |
| `quarantined` | No records were accepted; at least one record requires isolation or manual remediation |
| `empty` | No accepted, rejected, or quarantined records were present |

`portfolio_common.ingestion_evidence.classify_ingestion_outcome` encodes this status vocabulary for
future validation-report DTO wiring.

## Partial Rejection Rules

Partial rejection is allowed only when:

1. record-level identity is available,
2. accepted records are independently valid,
3. rejected or quarantined records cannot corrupt accepted records,
4. accepted count, rejected count, and quarantined count are explicit,
5. replay scope can target failed record keys without reprocessing accepted keys unless requested,
6. downstream event publication is idempotent for duplicate accepted records.

Partial rejection is not allowed when:

1. batch-level consistency is mandatory,
2. one failed record invalidates aggregate totals,
3. source order changes financial meaning,
4. validation cannot identify the failed source record,
5. a replay would create ambiguous duplicate domain events.

## Replay And DLQ Evidence Contract

Replay and DLQ evidence must include:

1. replay id,
2. replay fingerprint,
3. source batch fingerprint,
4. original ingestion job id or consumer DLQ event id,
5. replay scope: full batch, record-key subset, or DLQ-correlated payload,
6. replay status,
7. publish status,
8. bookkeeping status,
9. duplicate-blocking evidence,
10. operator reason and actor where available,
11. before/after failure state,
12. repair recommendation.

Replay status vocabulary:

| Status | Meaning |
| --- | --- |
| `dry_run` | Replayability was validated but no publish was attempted |
| `replayed` | Payload was republished and replay bookkeeping succeeded |
| `duplicate_blocked` | Equivalent replay already succeeded and was blocked |
| `failed` | Publish or validation failed before successful replay |
| `replayed_bookkeeping_failed` | Publish succeeded but post-publish bookkeeping failed |

`replayed_bookkeeping_failed` must remain distinct from `failed` because the payload may already have
reached Kafka and a blind retry could duplicate work.

## Retention And Repair Posture

Target retention classes:

1. raw source payload,
2. validation report,
3. rejected record evidence,
4. quarantine evidence,
5. replay audit,
6. DLQ event evidence,
7. repair decision evidence.

Retention rules must be explicit before production migration:

1. validation reports and replay audit records must outlive downstream recalculation windows,
2. raw source payload retention must support regulated audit and customer dispute workflows,
3. quarantined evidence must be retained until repair, rejection finalization, or governed expiry,
4. repair decisions must record actor, reason, timestamp, and affected source record keys.

## Boundary Rules

`lotus-core` owns:

1. source batch identity,
2. ingestion validation evidence,
3. record-level failure and quarantine evidence,
4. replay and DLQ repair supportability,
5. idempotency and duplicate replay prevention.

`lotus-core` does not own:

1. upstream adapter file polling,
2. vendor-specific source acquisition logic,
3. downstream analytics interpretation of accepted records,
4. UI-specific repair workflows outside source evidence and command contracts.

## Gaps To Close Later

| Gap | Owner slice |
| --- | --- |
| Runtime `IngestionEvidenceBundle` DTO | Slice 6 or ingestion runtime hardening |
| Validation report persistence/retention fields | Future migration slice |
| Uniform validation profile/version on all ingestion routes | Future ingestion contract slice |
| Record-key scoped replay across every payload family | Future replay hardening |
| Source batch fingerprint in replay and DLQ responses | Future replay contract slice |
| Platform retention policy alignment | Slice 9 |

## Validation

Slice 4 validation is:

1. `python -m pytest tests/unit/libs/portfolio-common/test_ingestion_evidence.py -q`,
2. `python -m ruff check src/libs/portfolio-common/portfolio_common/ingestion_evidence.py tests/unit/libs/portfolio-common/test_ingestion_evidence.py --ignore E501,I001`,
3. `python -m ruff format --check src/libs/portfolio-common/portfolio_common/ingestion_evidence.py tests/unit/libs/portfolio-common/test_ingestion_evidence.py`,
4. `git diff --check`,
5. `make lint`.
