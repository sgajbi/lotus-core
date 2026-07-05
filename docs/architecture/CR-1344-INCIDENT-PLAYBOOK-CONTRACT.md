# CR-1344 Incident Playbook Contract

## Objective

Locally fix GitHub issue #617 by turning operational incident guidance into a guarded playbook
contract with complete operator fields and safe-command checks.

## Finding

`docs/operations-runbook.md` and wiki pages had useful operational fragments, but they did not
provide a deterministic incident path for the major `lotus-core` runtime failure families. The
missing structure made it possible to document symptoms without API checks, containment actions,
escalation, post-incident evidence, or safe database boundaries.

## Changes

- Added `contracts/operations/incident-playbooks.v1.json` with eleven required incident families:
  ingestion stuck/failed, DLQ growth, replay failure, outbox backlog, valuation/aggregation lag,
  stale source data, reconciliation failure, readiness failure, database connectivity, Kafka
  connectivity, and security/audit denial spikes.
- Added `scripts/incident_playbook_guard.py` and focused guard tests.
- Added `make incident-playbook-guard`.
- Wired the guard into `make quality-wiki-docs-gate`, `make docs-evidence-pack`, and `make lint`.
- Added `docs/operations/Incident-Playbooks.md` and updated operations runbook/wiki surfaces.
- Updated repository context and validation wiki source.

## Compatibility Impact

No runtime route, request DTO, response DTO, OpenAPI schema, database schema, Kafka contract,
metric name, Dockerfile, deployment topology, package import path, or public runtime behavior
changed. This is operator documentation, evidence, and validation-governance hardening.

## Validation Evidence

Focused validation before commit:

```powershell
python scripts/incident_playbook_guard.py
python -m pytest tests/unit/scripts/test_incident_playbook_guard.py -q
python -m ruff check scripts/incident_playbook_guard.py tests/unit/scripts/test_incident_playbook_guard.py scripts/generate_documentation_evidence_pack.py --ignore E501,I001
make quality-wiki-docs-gate
make docs-evidence-pack
```

## Documentation And Wiki

Updated repo-authored docs and wiki source. Wiki publication remains a post-merge action through
the governed `Sync-RepoWikis.ps1 -Publish -Repository lotus-core` flow.

## Guidance Decision

Repo-local context changed because incident playbooks now have a canonical contract and guard. No
platform skill change is required; existing backend delivery and codebase-review guidance already
requires deterministic guards for repeatable documentation and operations drift.
