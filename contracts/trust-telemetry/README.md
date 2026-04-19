# Lotus Core Trust Telemetry

This directory contains repo-owned RFC-0087 trust telemetry snapshots for governed `lotus-core`
domain products.

The current first-wave snapshot is:

1. `portfolio-state-snapshot.telemetry.v1.json`
   Runtime trust proof for `lotus-core:PortfolioStateSnapshot:v1`.

Validate locally with:

```powershell
python -m pytest tests\unit\test_trust_telemetry.py -q
```

When `../lotus-platform` is available, the test validates the snapshot with the platform
`automation/validate_trust_telemetry.py` contract validator and checks that observed trust metadata
matches the repo-native declaration in `contracts/domain-data-products/lotus-core-products.v1.json`.
