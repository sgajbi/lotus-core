# Time And ID Provider Policy

Application use cases should receive time, monotonic timer, and ID providers instead of calling
system globals directly.

## Provider Types

1. Clock: returns current UTC `datetime`.
2. Date provider: returns current business or calendar `date` when no as-of date is supplied.
3. Monotonic timer: returns monotonic seconds for elapsed-duration measurement.
4. ID generator: returns deterministic ID components or UUID strings.

## Required Usage

Use provider injection in:

1. application/use-case services;
2. domain policies that need current time or generated IDs;
3. audit/replay workflows where timestamps, expiry, or generated evidence IDs affect behavior;
4. response builders that expose generated metadata.

## Allowed Direct Calls

Direct `datetime.now`, `date.today`, `uuid4`, and `time.monotonic` calls are allowed only in:

1. runtime provider adapters;
2. infrastructure code where the timestamp/ID is not domain behavior;
3. legacy modules recorded as follow-up hotspots until migrated.

## Current Representative Coverage

1. Financial reconciliation services use injected monotonic timer and finding ID generator providers.
2. Financial reconciliation repository run IDs can use an injected run-ID suffix provider.
3. Simulation service accepts injected clock and ID generator providers for sessions, expiry, and
   changes.
4. Core snapshot service accepts an injected clock for generated source-data metadata.
5. `tests/unit/scripts/test_time_provider_guard.py` prevents the representative provider-controlled
   paths from reintroducing direct global time or UUID calls.
