# CR-176 - HTTP Bootstrap Lineage Header Normalization Review

## Scope
- `src/libs/portfolio-common/portfolio_common/http_app_bootstrap.py`
- `tests/integration/services/query_service/test_main_app.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `tests/integration/services/event_replay_service/test_event_replay_app.py`

## Finding
The shared pure-HTTP bootstrap middleware still trusted incoming `X-Correlation-ID`, `X-Request-Id`, and `X-Trace-Id` headers verbatim. If a caller sent `"<not-set>"` or an empty value, the service echoed that sentinel back into response headers and log context instead of treating it as missing lineage.

## Change
- Normalized incoming HTTP lineage headers through `normalize_lineage_value(...)`.
- Missing or sentinel correlation ids now generate a fresh service-scoped correlation id.
- Missing or sentinel request ids now generate a fresh request id.
- Missing or sentinel trace ids now generate a fresh trace id.
- Added integration proofs for `query_service`, `query_control_plane_service`, and `event_replay_service`.

## Result
All pure HTTP apps that use the shared bootstrap now reject sentinel lineage at the boundary and emit clean response headers and log context.

## Follow-up
- Apply the same explicit normalization rule anywhere a non-HTTP transport still accepts raw external lineage values before entering the shared persistence/runtime layers.
