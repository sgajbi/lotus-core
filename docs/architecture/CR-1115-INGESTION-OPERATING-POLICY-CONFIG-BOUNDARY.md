# CR-1115: Ingestion Operating-Policy Config Boundary

Date: 2026-06-20

## Scope

`IngestionJobService.get_operating_policy()` still assembled the full
`IngestionOperatingPolicyConfig` inline from runtime settings, operating-band settings, replay
guardrails, worker cadence, scheduler cadence, DLQ budget, calculator lag thresholds, and
partition/replay strategy values. The operating-policy module already owned response
normalization, fingerprinting, and DTO construction, so runtime-policy mapping belonged with that
same boundary.

## Change

- Added `build_operating_policy_config(...)` to `ingestion_operating_policy.py`.
- Kept `IngestionJobService.get_operating_policy()` as a thin delegate that supplies the runtime
  policy and existing operating-band policy.
- Removed service-local runtime-policy aliases that were only needed for inline policy config
  assembly.
- Added direct helper coverage proving runtime settings map to policy config fields and calculator
  lag thresholds are copied defensively.

## Evidence

Local proof:

- `python -m pytest tests/unit/services/ingestion_service/services/test_ingestion_operating_policy.py tests/unit/services/ingestion_service/services/test_ingestion_job_service_guardrails.py -q`
- `python -m pytest tests/unit/services/ingestion_service/services -q`
- `make lint`
- `make typecheck`
- `make quality-maintainability-gate`
- `make quality-complexity-gate`
- `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`
- `git diff --check`
- Radon reports `IngestionJobService.get_operating_policy` remains `A (1)`,
  `ingestion_job_service.py` remains A-ranked at `A (100.00)`, and
  `ingestion_operating_policy.py` remains A-ranked at `A (58.22)`.

## Follow-Up

Continue extracting ingestion facade responsibilities only when the target helper owns the
corresponding policy or read-model boundary and local tests can pin the operator-facing behavior.
