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
| Dependency technology inventory | `make dependency-technology-inventory` | Validates exact locked package identities, license classifications, and release/advisory review evidence; emits a non-certifying receipt when review remains. |
| Dependency technology certification | `make dependency-technology-certify` | Fails closed unless every locked component has current explicitly approved evidence. |
| Static application boundaries | `make typecheck` | Includes the complete QCP analytics application/domain/ports boundary and its SQL adapters. |
| Documentation truth | `make docs-evidence-pack` | Captures README, wiki, API, RFC, supported-feature, and runbook checks in one manifest. |

## Lane Model

`lotus-core` uses:

1. `Remote Feature Lane`
2. `Pull Request Merge Gate`
3. `Main Releasability Gate`

The `automerge` label is consumed only by the small PR Auto Merge workflow. Applying that label
does not route to, cancel, or duplicate the full Pull Request Merge Gate for an unchanged head SHA.
Code-changing `synchronize` events still invalidate stale-head work and run the complete protected
gate for the new immutable head. Opened, reopened, and ready-for-review events retain their current
full-gate behavior; broader same-head evidence reuse is outside this bounded control.

### Required Check Authority

`contracts/ci/required-status-checks.v1.json` is the single versioned authority for branch
protection. It binds each required context to the GitHub Actions application ID, expands every
Pull Request Merge Gate matrix suite, and includes all 14 Quality Baseline `... Gate` jobs.
`Quality Baseline / Report Only` is the sole explicit advisory context; it retains diagnostics but
cannot authorize merge.

`make required-status-checks-guard` compares that manifest with both governed workflows and fails
on a missing or stale check, undeclared gate/advisory job, duplicate context, malformed matrix, or
wrong manifest shape. It is part of `make lint`, alongside `make quality-import-boundary-gate`, so
the local/Feature/PR/Main enforcement path cannot silently omit either control.

Main Releasability additionally runs `make required-status-checks-live-guard`. The command uses a
dedicated fine-grained `LOTUS_BRANCH_PROTECTION_READ_TOKEN` with repository Administration
read-only authority and compares strict mode plus the complete `(context, app_id)` set. The default
workflow token cannot read branch protection and must not be used; missing read authority or drift
fails exact-main evidence closed. Operators update branch protection only after all manifest-owned
contexts are green on the exact PR head. Generate the atomic PATCH body with
`required_status_checks_guard.py --print-desired-protection`; never hand-assemble or incrementally
mutate the 37-entry set.

Feature and PR lanes may restore `.cache/dependency-health` using a key derived from Python,
platform, installer, dependency/packaging manifests, locks, and the cache implementation. A verified
miss is saved immediately after dependency proof rather than after unrelated job gates. Main and
scheduled releasability always run `make verify-dependencies-clean`. Machine-readable clean and audit
reports are uploaded from `output/dependency-health/`; a cache hit never substitutes for the separate
mainline clean-install report.

Protected dependency-lock replay seeds pip-tools from the committed Linux or Windows tooling lock.
This proves that the reviewed closure still satisfies governed inputs without allowing a newly
published compatible transitive release to change the result between Feature, PR, and Main runs.
`make compile-ci-tooling-lock` is the explicit fresh-resolution path; its complete lock and
technology-evidence diff must be reviewed before merge.

Feature, PR, and main lanes also upload
`output/dependency-technology/inventory-receipt.json`, bound to the executing Git SHA and committed
inventory digest. A structurally valid but blocked classification is retained as evidence in the
report-only pilot lane. Missing or drifted evidence writes an unavailable failure receipt and fails
the job. The explicit certification target also fails when any component is missing, ambiguous,
compound, stale, yanked, pre-release, or otherwise not approved. A potentially allowed inventory
must additionally refetch every exact PyPI JSON authority, verify its canonical response digest,
and compare its yanked, upload-time, and raw license evidence with the recorded derived fields.
Report-only validation never emits release authority without that online revalidation. PyPI
release existence is not a support policy or vulnerability-disclosure channel. Upstream metadata
and popularity never create an implied support or legal approval.

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

The root pytest session also releases any reservation still held at session finish. This covers
unit-only and collection-only commands that never request the Compose fixture; Docker-backed
fixture teardown and session teardown share the same idempotent release path. A successful test
command must not defer socket cleanup to interpreter finalization.

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
scans and signs images, emits attestations/SBOMs, and writes evidence-bound candidate manifests.
Image Release uploads a separate versioned `image-scan-policy-<service>-attempt-<run-attempt>` receipt before
enforcing each immutable image decision. The receipt retains normalized Low, Medium, High, and
Critical finding identities and counts. Unknown severity is retained as an actionable,
non-exceptionable blocked finding rather than being collapsed into unavailable evidence. A Medium,
High, or Critical vulnerability or secret finding blocks all later
SBOM-export, signing, release-manifest, and deployment-rendering steps but preserves the secret-safe
receipt for remediation. Missing, malformed, wrong-digest, and inconsistent receipts fail closed;
a retained blocked receipt is not release certification.
One workflow-attempt authority bundle binds a freshly fetched official CISA KEV catalog version,
release/fetch times, entry count, source digest, and the pinned Platform exception-schema identity.
All 13 image jobs consume the same bundle. Known-exploited findings block at every severity. Missing,
malformed, below-baseline, stale, or unclassifiable exploitation evidence fails closed; Core never
infers KEV status from package name or severity. HTTPS-only redirects prevent source downgrade;
the reviewed completeness and anti-rollback boundary lives in
`contracts/security/cisa-kev-authority-policy.v1.json`.
Fetch, scan, or evaluation failure still uploads an exact-source, secret-safe reason-code receipt,
and enforcement rejects evidence older than 30 minutes or materially future-dated.
Receipts also bind the Core exception-register digest and its source-pinned Platform schema
authority. Medium, High, Critical, KEV, and unclassified exploitation findings remain blocking.
Exact exception records retain ownership evidence but cannot authorize release. Enforcement
reopens the retained report and authority files against the same immutable digest before signing
and again at the manifest boundary. The default register is empty, and
`make image-provenance-guard` rejects malformed ownership/approval/evidence, expiry, permanent
suppression, and wrong digest/advisory/severity matches.
The same command enforces the authored base-image lifecycle inventory. Core-built service images
must use the governed immutable Docker Official Python index and the release target must resolve to
the recorded `linux/amd64` child/config digests. Retained raw OCI index and child-manifest bytes are
hashed by the guard; the selected platform descriptor binds child media type, size, digest, and
config identity. Its retained OCI revision and exact Official Images source annotation also bind
the lifecycle source claim, so mutually consistent authored source fields are insufficient.
Protected PR and exact-main lanes run the read-only
`make base-image-registry-evidence-check`; `make refresh-base-image-manifest-evidence` is the
separate governed online refresh path.
Local CPython and Debian cutoffs cannot exceed
machine-readable upstream authority end dates. Complete credential-free Docker Official Images
identity evidence, exact-image Debian package-support status, ownership, and a maximum 30-day
evidence age are mandatory. An
available architecture in an OCI index is not by itself a supported production platform; external
Compose dependency images remain outside the Core-built release boundary.
Dependency technology validation independently recomputes component summaries and enforces fixed
non-certifying claims, repository/issue/generator identity, a reachable `origin/main` source
baseline plus exact lock/policy digests,
and a non-future generation timestamp. Its receipt binds the exact execution SHA. A blocked receipt
does not authorize production use or assert bank readiness.
Release manifest v2 binds the passed scan/authority receipt, CycloneDX bytes, Cosign GitHub Actions
certificate identity, signed SLSA subject, and governed `linux/amd64` base identities to one image
digest. It emits candidate posture and no promotions unless independent environment receipts exist;
the candidate workflow does not render a deployment. Image publication, signing, attestation, and
candidate manifests are limited to `main` and `v*` tags. Manual feature dispatch builds only
runner-local images and retains
normalized `diagnostic` scan receipts under read-only permissions. Diagnostic evidence cannot be
used by release enforcement and does not replace protected PR or exact-main proof.

## Repo-Native Lane Mapping

- `make ci-local`
  feature-lane parity
- `make ci`
  PR merge gate parity
- `make ci-main`
  main push releasability parity
- `make lint`
  complete-repository Ruff/format/import-boundary proof plus required-check, domain, and contract
  guards
- `make required-status-checks-guard`
  local manifest/workflow/matrix/advisory consistency proof
- `make required-status-checks-live-guard`
  exact-main read-only branch-protection `(context, app_id)` parity proof
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
  comparison evidence fails measured coverage closed. Governed Python paths outside `src/`,
  including exact changed Alembic migrations, remain in changed-critical selection.
  History-independent contract-only validation writes `critical-path-coverage-contract-report.json`
  and never replaces the measured report.
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
  release manifests, shared vulnerability authority, SBOM/provenance/signing/scan evidence binding,
  truthful candidate-versus-promotion posture, digest-based Kubernetes references,
  no-build-secret posture, and the shared `/version` endpoint
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
