# Integrations

## Who consumes `lotus-core`

- `lotus-gateway`
- `lotus-manage`
- `lotus-performance`
- `lotus-risk`
- `lotus-report`
- support tooling and QA flows

## Main integration surfaces

- operational reads from `query_service`
- analytics-input, snapshot, policy, and support contracts from `query_control_plane_service`
- write-ingress contracts from `ingestion_service`
- replay and operations control-plane contracts from `event_replay_service`
- reconciliation control execution contracts

## Important rule

Downstream consumers should use the correct family surface rather than treating `lotus-core` as one
undifferentiated API.

## Reference

- [RFC-0082 Contract Family Inventory](../docs/architecture/RFC-0082-contract-family-inventory.md)
