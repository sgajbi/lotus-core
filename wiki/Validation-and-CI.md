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
| Documentation truth | `make docs-evidence-pack` | Captures README, wiki, API, RFC, supported-feature, and runbook checks in one manifest. |

## Lane model

`lotus-core` uses:

1. `Remote Feature Lane`
2. `Pull Request Merge Gate`
3. `Main Releasability Gate`

## Repo-native lane mapping

- `make ci-local`
  feature-lane parity
- `make ci`
  PR merge gate parity
- `make ci-main`
  main push releasability parity
- `make test-institutional-release-gates`
  scheduled/manual institutional completion and sign-off parity

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
  repository/database hot paths, and API/error mapping. `make coverage-gate` also writes separate
  aggregate, changed-code, and critical-path coverage reports under `output/coverage/`.
- `make quality-wiki-docs-gate`
  validates repo-authored wiki source before publication by checking sidebar coverage, orphaned
  pages, publication-safe page names, first headings, and local relative links; when a published
  wiki clone is available, run `python scripts/wiki_validation_guard.py --published-wiki-dir <path>`
  to compare authored and published pages
- `make architecture-guard`
  protects layering and repository boundary posture
- `make image-provenance-guard`
  protects OCI image labels, CI build args, CI-only image publication, Git SHA image tags, digest
  release manifests, SBOM/provenance/signing/scan controls, digest-based Kubernetes references,
  same-image promotion evidence, no-build-secret posture, and the shared `/version` endpoint
- `make supported-features-guard`
  protects `docs/supported-features.md` and `wiki/Supported-Features.md` against unsupported
  capability claims, missing evidence links, stale feature status, and missing fail-closed or
  downstream ownership caveats
- `make incident-playbook-guard`
  protects executable incident playbooks for ingestion, DLQ, replay, outbox, valuation,
  aggregation, stale source data, reconciliation, readiness, database, Kafka, and security/audit
  incidents, including safe command and read-only database-check posture
- `make security-control-coverage-guard`
  protects the FastAPI app security-control matrix for standard bootstrap, secure headers, CORS,
  metrics access, auth/audit, payload limits, upload limits, allowlists, and safe errors

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
  expiry.

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
