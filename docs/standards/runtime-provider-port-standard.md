# Runtime Provider Port Standard

Application workflows that depend on current time, elapsed duration, or generated identifiers must
use injected provider ports instead of calling runtime capabilities directly.

## Required Pattern

1. Shared provider protocols and system adapters live in
   `portfolio_common.runtime_providers`.
2. Application and workflow services accept `Clock`, `MonotonicTimer`, and `IdGenerator` ports when
   they generate timestamps, TTLs, elapsed-duration metrics, session IDs, finding IDs, job IDs, or
   correlation IDs.
3. Unit tests use fake providers to prove generated metadata, expiry behavior, and elapsed
   duration deterministically.
4. Direct `datetime.now`, `date.today`, `uuid4`, and `perf_counter` calls are allowed in provider
   adapters, tests/fixtures, migration scripts, and explicitly documented transitional runtime or
   infrastructure adapters. They are not allowed inside provider-migrated application workflows.

## Representative Coverage

The current enforced slice protects:

1. financial reconciliation elapsed-duration and finding-ID generation,
2. core snapshot generated metadata timestamps,
3. simulation session ID, change ID, creation timestamp, TTL, and expiry behavior.

Broader legacy query-service analytics and operations services still contain direct wall-clock
calls and should migrate behind the same provider ports when those workflows are refactored.

## Enforcement

`make architecture-guard` runs `scripts/runtime_provider_port_guard.py`, which verifies the shared
provider module, the representative workflow usage, and the absence of direct runtime capability
calls in provider-migrated workflows.
