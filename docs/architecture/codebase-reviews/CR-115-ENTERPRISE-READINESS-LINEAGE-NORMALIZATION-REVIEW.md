## CR-115: Enterprise readiness lineage sentinel normalization

### Scope
- query-service enterprise audit middleware
- query-control-plane enterprise audit middleware

### Finding
Both enterprise-readiness middleware implementations still treated the default ambient context sentinel `"<not-set>"` as a real correlation id. That meant deny/write audit events could record poisoned client-visible lineage metadata even when no real correlation id had been established.

### Change
- Added correlation normalization in both enterprise-readiness implementations so `None`, empty string, and `"<not-set>"` collapse to `None` before audit emission.
- Added unit coverage for both deny and successful write audit paths in both owners.
- Renamed the control-plane unit module to a unique basename to eliminate collection collisions.

### Follow-up
Apply the same normalization rule to any remaining middleware or API helpers that echo ambient lineage state into logs, audits, or client-visible metadata.

### Evidence
- `src/services/query_service/app/enterprise_readiness.py`
- `src/services/query_control_plane_service/app/enterprise_readiness.py`
- `tests/unit/services/query_service/test_enterprise_readiness.py`
- `tests/unit/services/query_control_plane_service/test_control_plane_enterprise_readiness.py`
- `python -m pytest tests/unit/services/query_service/test_enterprise_readiness.py tests/unit/services/query_control_plane_service/test_control_plane_enterprise_readiness.py -q`
