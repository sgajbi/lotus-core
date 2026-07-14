# Validation and CI

## Current Scope

This page maps `lotus-core` validation commands to the contracts they protect. Use it to choose the
smallest evidence command for a change, then cite generated artifacts from the relevant gate or from
`make docs-evidence-pack`.

| Need | Primary Evidence | Notes |
|---|---|---|
| Local feature confidence | `make ci-local` | Fastest repo-native feature-lane parity check. |
| PR merge readiness | `make ci` | Pull-request merge-gate parity before opening or updating a PR. |
| Release/main posture | `make ci-main` | Main-push releasability parity. |
| Dependency consistency | `make verify-dependencies` | Reuses only an exact, integrity-checked environment. |
| Clean dependency proof | `make verify-dependencies-clean` | Always bootstraps without a cache read; required on main. |
| Vulnerability posture | `make security-audit` | Rechecks the environment and runs `pip-audit`. |
| Static application boundaries | `make typecheck` | Includes the complete QCP analytics application/domain/ports boundary and its SQL adapters. |
| Documentation truth | `make docs-evidence-pack` | Captures README, wiki, API, RFC, supported-feature, and runbook checks in one manifest. |

## Lane Model

`lotus-core` uses:

1. `Remote Feature Lane`
2. `Pull Request Merge Gate`
3. `Main Releasability Gate`

Feature and PR lanes may restore `.cache/dependency-health` using a key derived from Python,
platform, installer, dependency/packaging manifests, locks, and the cache implementation. A verified
miss is saved immediately after dependency proof rather than after unrelated job gates. Main and
scheduled releasability always run `make verify-dependencies-clean`. Machine-readable clean and audit
reports are uploaded from `output/dependency-health/`; a cache hit never substitutes for the separate
mainline clean-install report.

## Runtime Image Evidence

PR Merge Gate and Main Releasability each use one exact-source runtime image set. The required
`Validate Docker Build` job builds the workflow's service union once, records build timings, and
uploads a one-day transport bundle. Docker smoke, E2E, latency, load, validation, recovery, and
institutional jobs load that bundle instead of rebuilding overlapping images.
Workflow consumers set `LOTUS_RUNTIME_IMAGE_SET_VERIFIED=true` only after this handoff succeeds;
that explicit proof suppresses runtime rebuild flags, while ordinary CI and local commands retain
their normal build behavior. The E2E image inventory is checked against every repo-built full-stack
service so a newly started service cannot bypass exact-source verification.

Each Compose-backed suite also owns a unique `PreparedTestRuntime`, subprocess environment, and
held dynamic host-port reservation. The reservation is released only when Compose attempts
startup. A host bind conflict triggers cleanup, a complete new dynamic port generation, refreshed
database/Kafka/HTTP endpoints, and a bounded retry. Explicit operator port overrides are preserved.
Exhausted retries name the failure class, attempts, reallocations, and Compose project so a
collision is distinguishable from application startup failure.

Local image builds complete while reservations remain held; the subsequent startup does not use
`up --build`. This keeps build duration outside the host-bind race interval.

Latency, performance-load, Docker-smoke, institutional-completion, and failure-recovery are managed
validation runs. Each allocates a fresh project and ports, derives its service/database endpoints
from that runtime, captures a log naming the exact project and compose file, and then tears down.
Failure recovery also binds migration polling and interruption lookup to that project and writes
`output/task-runs/diagnostics/failure-recovery-gate-compose.log`. CI uploads owner-produced logs
from `output/task-runs/diagnostics/`; a post-run default-project log command is not valid evidence.
External targets remain available through `--skip-compose`, and keeping a stack requires an
explicit local diagnosis flag.

Failure-recovery JSON and Markdown evidence records each transaction, cost, cashflow, position,
claim, and lag predicate with actual/expected values, comparison, satisfaction, and source UTC
last-change time. A timeout must therefore identify the fields that remained unsatisfied.
An exact-count overshoot or DLQ increase from the pre-interruption baseline is terminal evidence;
polling records the reason and stops without another wait cycle.

| Evidence | Location | Failure Meaning |
|---|---|---|
| Build timing | `output/runtime-image-set/build-metrics.json` | Compare unique builds, reused tags, and total producer time. |
| Image-set manifest | `output/runtime-image-set/manifest.json` | Source, dependency, image, or bundle identity is incomplete or mismatched. |
| Portable bundle | `output/runtime-image-set/images.tar` | Ephemeral same-workflow transport only; never a promoted release image. |
| Consumer verification | `runtime_image_set.py load-verify` | Fails before stack startup on wrong SHA, tampering, stale images, or OCI-label drift. |

The manifest identifies Git commit, branch, repository, CI run, generated-at time, service image
IDs, Dockerfile hashes, Compose hash, dependency-lock hash, dependency-closure hash, bundle digest,
and manifest content hash. Release publication remains separate: only Image Release pushes to GHCR,
scans and signs images, emits attestations/SBOMs, and records digest-based promotion evidence.

## Repo-Native Lane Mapping

- `make ci-local`
  feature-lane parity
- `make ci`
  PR merge gate parity
- `make ci-main`
  main push releasability parity
- `make lint`
  complete-repository Ruff check and format proof plus governed domain and contract guards
- `make test-institutional-release-gates`
  scheduled/manual institutional completion and sign-off parity
- `make test-transaction-processing-contract`
  DB-direct combined transaction-processing contract; blocking in PR and main lanes
- `make verify-dependencies`
  exact-key dependency-health cache with marker and `pip check` integrity proof
- `make verify-dependencies-clean`
  operator/mainline clean-install proof and explicit cache bypass
- `make typecheck`
  configured static boundary proof, including QCP analytics adapter-record and port conformance

## Important gates

- `make route-contract-family-guard`
- `make source-data-product-contract-guard`
- `make analytics-input-consumer-contract-guard`
- `make event-runtime-contract-guard`
- `make rfc0083-closure-guard`
- `make rfc-status-ledger-guard`
- `make openapi-gate`
- `make quality-openapi-spectral-gate`
- `make api-route-catalog-guard`
- `make front-door-sync-guard`
- `make quality-wiki-docs-gate`
- `make docs-evidence-pack`
- `make critical-path-coverage-guard`
- `make architecture-guard`
- `make image-provenance-guard`
- `make security-control-coverage-guard`
- `make test-transaction-processing-contract`

## Guard-to-contract mapping

- `make route-contract-family-guard`
  keeps RFC-0082 route-family ownership aligned with the route registry and contract-family
  placement
- `make source-data-product-contract-guard`
  keeps source-data product naming, metadata, and publication semantics aligned with RFC-0083
- `make analytics-input-consumer-contract-guard`
  protects downstream analytics-input consumer expectations
- `make event-runtime-contract-guard`
  protects eventing and supportability contract posture
- `make rfc0083-closure-guard`
  protects the machine-readable RFC-0083 implementation-closure ledger
- `make rfc-status-ledger-guard`
  protects the repository-wide RFC status ledger across core RFCs, transaction RFC/spec documents,
  architecture RFC material, and operations RFC playbooks
- `make openapi-gate`
  protects consumer-facing contract quality and OpenAPI completeness
- `make quality-openapi-spectral-gate`
  generates stable per-service OpenAPI artifacts under `output/openapi/` and enforces the portable
  Spectral blocker subset for operation IDs, descriptions, summaries, tags, and common successful
  `2xx` responses
- `make api-route-catalog-guard`
  protects the generated API route catalog against drift from FastAPI OpenAPI output and
  route-family governance metadata
- `make front-door-sync-guard`
  protects README, wiki home/sidebar, canonical documentation links, and PR documentation
  no-change decision terms
- `make critical-path-coverage-guard`
  protects the critical-path coverage contract for transaction lifecycle, calculations,
  position/cash state, corporate actions, auth/audit/security, ingestion/replay/outbox,
  repository/database hot paths, and API/error mapping. `make coverage-gate` writes a scoped Query
  Service aggregate artifact, broader measured-source evidence, and a changed/critical-path report
  under `output/coverage/`. The report retains rename/copy/delete lineage, excludes deleted paths
  from current-file counts, and fails with `CHANGED_CRITICAL_SOURCE_UNMEASURED` when a current
  changed critical module is absent from the governed coverage execution. Measured changed
  critical modules must pass both the contract's line and branch thresholds; unavailable Git
  comparison evidence also fails closed.
- `make generated-artifact-tracking-guard`
  fails if disposable build, cache, package, coverage, or generated `output/` artifacts become
  tracked repository source truth. Local ignored generated artifacts remain removable through
  `make clean`.
- `make quality-wiki-docs-gate`
  validates repo-authored wiki source before publication by checking sidebar coverage, orphaned
  pages, publication-safe page names, first headings, and local relative links; when a published
  wiki clone is available, run `python scripts/quality/wiki_validation_guard.py --published-wiki-dir <path>`
  to compare authored and published pages
- `make architecture-guard`
  protects layering and repository boundary posture
- `make image-provenance-guard`
  protects OCI image labels, CI build args, CI-only image publication, Git SHA image tags, digest
  release manifests, SBOM/provenance/signing/scan controls, digest-based Kubernetes references,
  same-image promotion evidence, no-build-secret posture, and the shared `/version` endpoint
- `make supported-features-guard`
  protects `docs/features/supported-features.md` and `wiki/Supported-Features.md` against unsupported
  capability claims, missing evidence links, stale feature status, and missing fail-closed or
  downstream ownership caveats
- `make incident-playbook-guard`
  protects executable incident playbooks for ingestion, DLQ, replay, outbox, valuation,
  aggregation, stale source data, reconciliation, readiness, database, Kafka, and security/audit
  incidents, including safe command and read-only database-check posture
- `make security-control-coverage-guard`
  protects the FastAPI app security-control matrix for standard bootstrap, secure headers, CORS,
  metrics access, auth/audit, payload limits, upload limits, allowlists, and safe errors
- `make test-transaction-processing-contract`
  protects atomic combined cost, cashflow, position, replay, rollback, fee, FX, multi-lot,
  backdated correction, epoch rebuild, and one-event-per-input behavior
- required external Docker images use bounded retry for classified registry/network and unknown
  failures; explicit permanent tag/auth errors fail immediately, unknown failures fail closed after
  the bounded budget, and raw registry output is never returned
- `make profile-cost-processing-modes`
  characterizes ordered lot-opening append, state-dependent disposal append, and deterministic
  backdated rebuild without claiming database or Kafka throughput

## What the gates protect

- route-family ownership
- analytics-input governance
- source-data product semantics
- eventing and supportability posture
- OpenAPI quality
- portable Spectral OpenAPI linting
- generated API route catalog coverage
- README/wiki front-door synchronization
- wiki source publication readiness
- aggregate, changed-code, and critical-path coverage reporting
- architecture boundaries
- image provenance, release supply-chain, and runtime version metadata
- production-readiness closure evidence
- RFC status, ownership, evidence, supported-feature, registry, wiki, and supersession metadata
- FastAPI security-control coverage

## Reading path when a gate fails

- route-family or consumer guard failure:
  start with [RFC Index](RFC-Index), then [Architecture Index](../docs/architecture/README.md)
- event-runtime or supportability guard failure:
  start with [Operations Runbook](Operations-Runbook), then the RFC-0083 eventing/supportability
  docs from the architecture index
- architecture or OpenAPI guard failure:
  start with [Architecture](Architecture), [API Surface](API-Surface), the
  [generated API route catalog](../docs/standards/api-route-catalog.v1.json), and the deep
  architecture index before changing code or docs
- wiki docs gate failure:
  update repo-local `wiki/` source first, keep `_Sidebar.md` aligned with every publishable page,
  and run the optional published-wiki parity check only against a generated or cloned publication
  target
- security-control coverage failure:
  update `contracts/security/security-control-coverage.v1.json` and the app bootstrap together;
  do not add a matrix entry that claims live ingress, IAM, or WAF evidence without separate runtime
  proof
- critical-path coverage failure:
  update `docs/standards/critical-path-coverage.v1.json`, the affected tests, and the relevant
  Makefile suite together. Do not add an exception without owner, reason, follow-up issue, and
  expiry. Inspect `changed_file_lineage` before treating an old path as current: deletes are
  audit-only and renames are evaluated through their post-change path.

## Related references

- [RFC Index](RFC-Index)
- [Architecture Index](../docs/architecture/README.md)
- [Operations Runbook](Operations-Runbook)

## App-Level Validation Evidence

`make lotus-core-validate` is the repo-native app-level supported-surface validation command. It
runs contract checks and deterministic runtime smoke, writes machine-readable evidence under
`output/lotus-core-validation/`, and exits non-zero when proof is weak.

The PR Merge Gate runs this command as a blocking validation gate. The job checks out
`lotus-platform` into the workflow workspace and sets `LOTUS_PLATFORM_ROOT` before running the
command so domain-product contract validation uses the governed platform validator and vocabulary.
If static contracts, supported-feature truth, or deterministic runtime smoke fail, the PR gate fails
and still uploads the generated evidence for diagnosis.

## Documentation Evidence Pack

`make docs-evidence-pack` writes `output/documentation-evidence/documentation-evidence-pack.json`.
Use it for release, PR, and demo documentation review when README, wiki, API, RFC, runbook, or
supported-feature claims need one citable evidence source. The pack records the command, UTC
timestamp, git SHA, runtime profile, status, generated artifacts, affected documentation surfaces,
wiki validation, README/wiki front-door synchronization, API vocabulary generation, generated API
route catalog checks, critical-path coverage contract checks, RFC-0083 closure checks, RFC status
ledger checks, supported-feature truth, and runbook validation.
