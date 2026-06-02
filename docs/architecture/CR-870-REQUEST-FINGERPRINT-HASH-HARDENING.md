# CR-870: Request Fingerprint Hash Hardening

Status: Hardened on 2026-06-02.

## Finding

Bandit reported a high-severity `B324` weak-hash finding in core snapshot request fingerprint
generation. Related query-service request fingerprint helpers also used MD5 with local suppressions.

Request fingerprints are deterministic request identity values, not secret-bearing authentication
material, but retaining MD5 created avoidable security debt and prevented a clean Bandit baseline.

## Change

Changed request fingerprint generation to SHA-256 by:

1. updating the shared `request_fingerprint(...)` helper to use SHA-256,
2. routing core snapshot fingerprints through the shared helper,
3. routing analytics-timeseries fingerprints through the shared helper,
4. removing remaining MD5 usage from `src` and `tests`,
5. adding focused coverage that the shared fingerprint uses the expected SHA-256 hex length.

The Bandit baseline is reduced from 17 findings to 16 findings, with zero high-severity findings
remaining.

## Boundary Preserved

This change preserves:

1. deterministic request identity,
2. key-order-stable fingerprint payload serialization,
3. API response shape,
4. database schema,
5. runtime service behavior outside fingerprint value length/content.

## Wiki Decision

No repo-local `wiki/` source update is included. This is a security hardening and quality-baseline
ratchet recorded in the repo-local quality reports and architecture review ledger; it does not
change operator-facing runtime behavior.

## Validation

Local validation passed for the slice:

1. focused request-fingerprint and core-snapshot tests: 47 passed,
2. focused analytics-timeseries tests: 69 passed,
3. `python -m bandit -r src -c pyproject.toml` baseline measurement: 16 findings, 0 high,
4. MD5 source search: no `hashlib.md5`, `from hashlib import md5`, or `md5(...)` usage remains
   under `src` or `tests`,
5. `make quality-ruff-gate`,
6. `make quality-ruff-format-gate`,
7. `make typecheck`,
8. `git diff --check`.
