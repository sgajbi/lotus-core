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
  main releasability parity

## Important gates

- `make route-contract-family-guard`
- `make source-data-product-contract-guard`
- `make analytics-input-consumer-contract-guard`
- `make event-runtime-contract-guard`
- `make rfc0083-closure-guard`
- `make openapi-gate`
- `make architecture-guard`

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
- `make architecture-guard`
  protects layering and repository boundary posture

## What the gates protect

- route-family ownership
- analytics-input governance
- source-data product semantics
- eventing and supportability posture
- OpenAPI quality
- architecture boundaries
- production-readiness closure evidence

## Reading path when a gate fails

- route-family or consumer guard failure:
  start with [RFC Index](RFC-Index), then [Architecture Index](../docs/architecture/README.md)
- event-runtime or supportability guard failure:
  start with [Operations Runbook](Operations-Runbook), then the RFC-0083 eventing/supportability
  docs from the architecture index
- architecture or OpenAPI guard failure:
  start with [Architecture](Architecture), [API Surface](API-Surface), and the deep architecture
  index before changing code or docs

## Related references

- [RFC Index](RFC-Index)
- [Architecture Index](../docs/architecture/README.md)
- [Operations Runbook](Operations-Runbook)
