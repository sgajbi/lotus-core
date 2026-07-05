# Validation and CI

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
- `make openapi-gate`
- `make quality-openapi-spectral-gate`
- `make quality-wiki-docs-gate`
- `make docs-evidence-pack`
- `make architecture-guard`
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
- `make openapi-gate`
  protects consumer-facing contract quality and OpenAPI completeness
- `make quality-openapi-spectral-gate`
  generates stable per-service OpenAPI artifacts under `output/openapi/` and enforces the portable
  Spectral blocker subset for operation IDs, descriptions, summaries, tags, and common successful
  `2xx` responses
- `make quality-wiki-docs-gate`
  validates repo-authored wiki source before publication by checking sidebar coverage, orphaned
  pages, publication-safe page names, first headings, and local relative links; when a published
  wiki clone is available, run `python scripts/wiki_validation_guard.py --published-wiki-dir <path>`
  to compare authored and published pages
- `make architecture-guard`
  protects layering and repository boundary posture
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
- wiki source publication readiness
- architecture boundaries
- production-readiness closure evidence
- FastAPI security-control coverage

## Reading path when a gate fails

- route-family or consumer guard failure:
  start with [RFC Index](RFC-Index), then [Architecture Index](../docs/architecture/README.md)
- event-runtime or supportability guard failure:
  start with [Operations Runbook](Operations-Runbook), then the RFC-0083 eventing/supportability
  docs from the architecture index
- architecture or OpenAPI guard failure:
  start with [Architecture](Architecture), [API Surface](API-Surface), and the deep architecture
  index before changing code or docs
- wiki docs gate failure:
  update repo-local `wiki/` source first, keep `_Sidebar.md` aligned with every publishable page,
  and run the optional published-wiki parity check only against a generated or cloned publication
  target
- security-control coverage failure:
  update `contracts/security/security-control-coverage.v1.json` and the app bootstrap together;
  do not add a matrix entry that claims live ingress, IAM, or WAF evidence without separate runtime
  proof

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
wiki validation, API vocabulary generation, RFC ledger checks, supported-feature truth, and runbook
validation.
