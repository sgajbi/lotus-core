# Development Workflow

## Normal working loop

1. load the smallest correct context
2. use repo-native commands
3. run targeted local proof
4. push early for GitHub-backed heavy validation
5. keep RFC-0082 and RFC-0083 architecture truth aligned with the code

## High-value commands

```bash
make ci-local
make route-contract-family-guard
make source-data-product-contract-guard
make analytics-input-consumer-contract-guard
make event-runtime-contract-guard
make rfc0083-closure-guard
```

## Important working rule

Because `lotus-core` has a heavy validation contract, do not reflexively run the full matrix for
every small change. Use targeted proof locally, then use GitHub for the expensive merge-gate work.
