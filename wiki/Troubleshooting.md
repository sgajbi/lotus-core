# Troubleshooting

## Common issues

### A route exists but you are unsure which service should own it

Use:

- [RFC-0082 Contract Family Inventory](../docs/architecture/RFC-0082-contract-family-inventory.md)
- [Query Service And Control Plane Boundary](../docs/architecture/QUERY-SERVICE-AND-CONTROL-PLANE-BOUNDARY.md)

### Shared runtime or ingress is broken

If the issue is shared infrastructure ownership, move to `lotus-platform` and its ingress/runtime
guidance.

### App-local stack started but services are still unhealthy

Check:

1. `docker compose ps`
2. `docker compose logs --tail=200 migration-runner`
3. `docker compose logs --tail=200 kafka-topic-creator`
4. `python -m alembic current`

### You need to diagnose portfolio processing state

Prefer support, lineage, replay, and reconciliation APIs before direct database inspection.

If runtime telemetry and database facts disagree, use durable database state as the source of truth
and record the rollout gap explicitly.

### Validation scope feels too expensive

Use targeted proof first:

- `python scripts/test_manifest.py --suite integration-lite --validate-only`
- `make test-unit-db`
- `make test-integration-lite`

Then move to GitHub-backed heavy validation for the full merge gate.

### Documentation looks like old PAS-era or ecosystem-level content

That material likely belongs in `lotus-platform`, not `lotus-core`.

See:

- `lotus-platform/wiki/Legacy-Core-Wiki-Migration-Ledger.md`
