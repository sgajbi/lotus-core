# CR-1552 Exact-Source CI Runtime Image Set

## Objective

Deliver the first bounded GitHub issue #730 slice by building repo-owned runtime images once per
workflow SHA, transporting the same images to Docker-backed jobs, and failing before stack startup
when source or image evidence does not match.

## Finding

PR Merge Gate run `29201114726` built overlapping Compose images independently in E2E smoke,
application validation, fast load, latency, and Docker smoke jobs. The five prebuild steps consumed
`1,666` aggregate runner-seconds; the slowest single prebuild took `375` seconds. Each job produced
local images independently, so there was no authoritative workflow image-set manifest proving that
all runtime gates exercised the same exact-source image identities.

The same pattern existed in Main Releasability. Four Compose services also reused the persistence
Dockerfile but were built separately with identical metadata.

## Change

- Added `runtime_image_set.py` to create, export, load, and verify portable CI image sets.
- Added ordered PR and main service unions as the single inventory for workflow image ownership.
- Expanded each workflow's existing `Validate Docker Build` job into the sole image-set producer.
- Replaced per-consumer Buildx/cache/prebuild blocks with artifact download and exact-SHA
  `load-verify` steps across PR and main Docker-backed jobs.
- Added manifest evidence for source commit, branch, repository, CI run, generated-at time, image
  IDs, Dockerfile hashes, Compose hash, dependency-lock hash, dependency-closure hash, bundle
  digest, and canonical content hash.
- Added fail-closed OCI revision, branch, source, version, CI run, and created-label checks.
- Corrected CI image-version precedence so the full source SHA wins over merge-ref names.
- Added per-service and total prebuild timing evidence.
- Coalesced identical Dockerfiles into one build plus local tags while preserving every Compose
  service image name.

## Measurement

| Evidence | Before | Local After | Remote After |
|---|---:|---:|---:|
| Repo-owned prebuild steps per PR workflow | `5` | `1` producer contract | Pending PR run |
| Aggregate PR prebuild runner time | `1,666s` | Not comparable for query-only proof | Pending PR run |
| Slowest PR prebuild | `375s` | Not comparable for query-only proof | Pending PR run |
| Query-only cold local build | Not measured | `47.305s` | Not applicable |
| Query-only portable bundle | Not available | `117,021,696` bytes | Not applicable |

Remote wall time, artifact upload/download time, stack startup, and gate duration must be read from
the exact-head PR run before claiming throughput improvement. The architecture reduces duplicate
build execution by construction; it does not pre-claim a wall-time reduction.

## Compatibility And Failure Posture

No application API, OpenAPI, financial calculation, database, migration, Kafka, production image,
or downstream contract changed. Existing required check names remain stable. The artifact is
ephemeral same-workflow transport with one-day retention; it is not pushed, signed, promoted, or
treated as a release image. Image Release remains the only GHCR publication path.

A wrong source SHA, changed Compose or dependency lock, altered manifest, changed bundle, missing
image, changed image ID, or OCI source-label mismatch fails before Docker Compose startup. External
vendor images remain governed by bounded pull/inspection logic and are not copied into the bundle.

## Validation

- Real query-service build, export, reload, and verification: passed.
- Runtime image-set unit tests: `5 passed`.
- Prebuild, service-union, workflow, action-version, and main-workflow focused tests: passed.
- Workflow YAML parsing and `actionlint`: passed.
- Scoped Ruff lint/format and `git diff --check`: passed.
- Wiki professional-page audit and repository documentation gates: passed.
- Repo-wiki check-only: expected drift only for `Validation-and-CI.md`; publish after merge.

## Remaining #730 Work

This slice does not close #730. Scenario sharding and change-impact selection, exact-SHA selective
dispatch, collision-resistant port reservation, controlled-failure diagnostic completeness,
field-level polling evidence, and p50/p95/flake/rerun trend reporting remain tracked there.

## Durable Guidance Decision

README, testing/CI strategy, script catalog, repository context, wiki source, workflows, and review
ledger changed. No central skill or platform context update is required: existing CI governance
already requires exact-SHA evidence, reusable immutable artifacts, truthful measurements, and a
separate clean release lane. This implementation specializes those rules for `lotus-core`.
