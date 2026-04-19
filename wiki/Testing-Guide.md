# Testing Guide

## Test posture

`lotus-core` has one of the heaviest validation contracts in Lotus.

That is intentional. This repository is the system of record for foundational portfolio,
transaction, valuation, supportability, and replay behavior.

## Main suite groups

### Fast local logic

- `make test`
- `make test-unit-db`

Use these when the change is mostly local logic, repository behavior, or schema-backed unit work.

### Integration and contract proof

- `make test-integration-lite`
- `make test-ops-contract`
- `make test-transaction-buy-contract`
- `make test-transaction-sell-contract`
- `make test-transaction-dividend-contract`
- `make test-transaction-interest-contract`
- `make test-transaction-fx-contract`
- `make test-transaction-portfolio-flow-bundle-contract`

Use these when route contracts, source-data handling, supportability, or transaction semantics are
at risk.

### Runtime and end-to-end proof

- `make test-e2e-smoke`
- `make test-docker-smoke`
- `make test-latency-gate`
- `make test-performance-load-gate`
- `make test-failure-recovery-gate`

Use these when the slice changes worker orchestration, event flow, runtime wiring, replay posture,
or production-grade operational behavior.

## Lane mapping

- `make ci-local`
  feature-lane parity
- `make ci`
  PR merge gate parity
- `make ci-main`
  main releasability parity

Because the repo is expensive to validate fully, the normal workflow is:

1. run the smallest credible local proof
2. add targeted guards or suites for the changed contract
3. rely on GitHub-backed heavy execution for the full merge gate

## Test manifest

Suite composition is governed by:

- [scripts/test_manifest.py](../scripts/test_manifest.py)

Useful manifest checks:

```bash
python scripts/test_manifest.py --suite integration-lite --validate-only
python scripts/test_manifest.py --suite integration-lite --print-args
```

Use the manifest instead of inventing ad hoc pytest selections when you need parity with CI.

## Guard rails that matter

`lotus-core` also treats several non-pytest gates as part of testing truth:

- `make architecture-guard`
- `make openapi-gate`
- `make api-vocabulary-gate`
- `make route-contract-family-guard`
- `make source-data-product-contract-guard`
- `make analytics-input-consumer-contract-guard`
- `make event-runtime-contract-guard`
- `make rfc0083-closure-guard`

If one of these fails, the change is not validated, even if a narrow pytest target passed.

## Test quality rules

1. add regression coverage for real contract or runtime defects
2. prefer deterministic proof over broad but noisy suites
3. test ownership boundaries when route or contract-family placement changes
4. test supportability and replay behavior when eventing or ops surfaces change
5. avoid superficial coverage that does not meaningfully protect the system-of-record contract
