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

## What the gates protect

- route-family ownership
- analytics-input governance
- source-data product semantics
- eventing and supportability posture
- OpenAPI quality
- architecture boundaries
- production-readiness closure evidence
