# CR-872: Enterprise Readiness Settings Lookup Hardening

Status: Hardened on 2026-06-02.

## Finding

After CR-871, Bandit still reported one low-severity `B105` finding in the shared enterprise
readiness runtime. The flagged value was not a credential. It was a string literal used as a typed
settings attribute name for the enterprise secret-rotation policy knob.

Even though the finding was a false positive, keeping secret-shaped literals in dynamic lookup code
made the security baseline noisier than necessary and delayed security-gate ratcheting.

## Change

Replaced the string-based integer setting lookup with explicit typed settings access for:

1. `ENTERPRISE_SECRET_ROTATION_DAYS`,
2. `ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES`.

The runtime still gives typed service settings precedence for supported enterprise integer knobs
and still delegates unknown integer names to the injected environment integer reader.

The Bandit baseline is reduced from 12 findings to 11 findings, with zero low-severity and
zero high-severity findings remaining.

## Boundary Preserved

This change preserves:

1. enterprise runtime policy validation behavior,
2. typed settings precedence over fallback environment integer reads,
3. API contracts,
4. database schema,
5. report-only security posture until the remaining medium findings are fixed or explicitly
   governed.

## Remaining Security Baseline

Bandit now reports 11 medium findings:

1. one low-confidence `B608` finding for the allowlisted reprocessing job `ORDER BY` clause,
2. ten `B104` findings for health-probe Uvicorn bind-all host literals in consumer managers.

These remain the next security-hardening targets before the Bandit gate can be enforced.

## Wiki Decision

No repo-local `wiki/` source update is included. This is a security baseline cleanup recorded in
the repo-local quality reports and architecture review ledger; it does not change operator-facing
runtime behavior.

## Validation

Local validation passed for the slice:

1. `python -m pytest tests\unit\libs\portfolio-common\test_enterprise_readiness_shared.py -q`:
   26 passed,
2. `python -m bandit -r src -c pyproject.toml` baseline measurement: 11 findings, 0 low, 0 high,
3. `make quality-ruff-gate`,
4. `make quality-ruff-format-gate`,
5. `make typecheck`,
6. `git diff --check`.
