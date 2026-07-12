# CR-149 - Enterprise Audit Payload Correlation Normalization Review

## Scope
- `src/services/query_service/app/enterprise_readiness.py`
- `src/services/query_control_plane_service/app/enterprise_readiness.py`
- corresponding unit tests

## Finding
Both enterprise-readiness middleware implementations already normalized missing correlation ids to `None` before calling `emit_audit_event(...)`. But the audit payload builder still serialized missing correlation as an empty string.

That meant the middleware contract was clean at the call site while the emitted audit record still leaked a transport-style sentinel.

## Fix
- Preserve `None` in the emitted audit payload instead of coercing it to `""`.
- Add direct unit proof for both owners.

## Result
Audit payloads now represent missing lineage as missing, which matches the rest of the normalized platform contract.
