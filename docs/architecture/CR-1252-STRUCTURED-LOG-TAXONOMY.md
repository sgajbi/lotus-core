# CR-1252: Structured Log Taxonomy

Date: 2026-07-01

## Objective

Fix GitHub issue #568 by making operational logs deterministic, source-safe, and guardable across
shared health, Kafka, outbox, ingestion reprocessing, query read, valuation replay, and scheduler
paths.

## Expected Improvement

The slice adds a shared `operation_log_extra(...)` helper that normalizes required taxonomy fields:

- `event_name`
- `operation`
- `status`
- `reason_code`

It also adds `log_operation_event(...)` for level-aware emission through the standard logger
methods, so tests that patch `logger.info`, `logger.warning`, or `logger.error` still observe the
same method calls.

Operational logs in the guarded paths now use constant messages plus structured fields. Portfolio,
account, client, security, request, correlation, and trace identifiers are not embedded in
free-text operational messages. Query and valuation logs retain useful support signals such as
counts, filter presence, as-of dates, retry outcomes, lifecycle phases, and bounded reason codes.

## Guardrail

`scripts/structured_log_guard.py` statically rejects:

1. f-string logger messages in guarded operational paths,
2. sensitive identifier variables passed as logger message-formatting arguments.

`make structured-log-guard` is wired into `make lint` so the same defect class is blocked before it
reaches PR CI.

## Tests Added

- `tests/unit/libs/portfolio-common/test_logging_utils.py`
  - taxonomy normalization
  - required structured fields
  - redaction through operation log extras
  - level-aware log emission
- `tests/unit/scripts/test_structured_log_guard.py`
  - rejects f-string operational log messages
  - rejects sensitive identifier formatting arguments
  - accepts constant messages with structured extras

Existing Kafka consumer and health tests were updated to assert stable event names and reason codes.

## Validation Evidence

Local evidence before commit:

- `python scripts\structured_log_guard.py` passed.
- `python -m pytest tests\unit\libs\portfolio-common\test_logging_utils.py tests\unit\libs\portfolio-common\test_kafka_consumer.py tests\unit\libs\portfolio-common\test_health.py tests\unit\scripts\test_structured_log_guard.py -q --tb=short` passed with 70 tests.
- Scoped `ruff check` and `ruff format --check` passed for the touched Python files.
- `make lint` passed, including `structured-log-guard`.
- `make typecheck` passed with no issues in 50 source files.
- `make quality-wiki-docs-gate` passed.
- `python C:\Users\Sandeep\projects\lotus-platform\codex\skills\lotus-readme-wiki-governance\scripts\audit_wiki_quality.py --wiki-dir wiki` passed.
- `git diff --check` passed.
- `powershell -ExecutionPolicy Bypass -File C:\Users\Sandeep\projects\lotus-platform\automation\Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core` reported expected pre-publication drift for `Operations-Runbook.md` and pre-existing drift for `Outbox-Events.md`.
- Stranded-truth reconciliation found only active Dependabot branches:
  `origin/dependabot/github_actions/github-actions-02325a8da5` and
  `origin/dependabot/pip/python-runtime-b808a9fc65`.

## Downstream Compatibility

No API route, response DTO, OpenAPI schema, Kafka topic, event payload, database schema, metric
name, or business behavior changed.

The only runtime-observable change is log shape: affected operational paths now emit stable
taxonomy fields and avoid embedding sensitive identifiers in message text.

## Documentation And Wiki Decision

Documentation changed because the repository now has a new operator-facing logging taxonomy and a
new blocking lint guard:

- `docs/observability.md`
- `docs/operations-runbook.md`
- `wiki/Operations-Runbook.md`
- `REPOSITORY-ENGINEERING-CONTEXT.md`
- `quality/quality_scorecard.md`
- `quality/refactor_health_report.md`

The repo-local wiki source is updated in this slice. Publication remains post-merge per the Lotus
wiki publication rule.
