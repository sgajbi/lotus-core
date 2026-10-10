# Imported model portfolio effective windows

Core owns admission and persistence of model definitions and instrument targets. The existing
`POST /ingest/model-portfolios` and `POST /ingest/model-portfolio-targets` endpoints require
`effective_to >= effective_from` whenever an end date is supplied. Both endpoints reject a
reversed window with HTTP 422 `INVALID_EFFECTIVE_WINDOW` and `ctx.field_path="effective_to"`
before command dispatch, job creation or source persistence. One invalid record rejects the batch.
Existing weight, band, duplicate-key, lineage, currency and approval-status rules still apply.

Both boundaries are inclusive. Equal dates represent a valid one-day window; null end dates are
open-ended. Valid historical and future observations remain admissible independently of today's
date. Readers select records effective on the requested business date and retain existing
approved-definition and target-status policies. This invariant grants no model approval.

## Request and response examples

The following one-day target preserves its exact source weight:

```json
{"model_portfolio_targets":[{"model_portfolio_id":"MODEL_EXAMPLE","model_portfolio_version":"v1","instrument_id":"EQ_EXAMPLE","target_weight":"0.6000000000","effective_from":"2026-09-01","effective_to":"2026-09-01"}]}
```

A one-day approved definition uses the same interval:

```json
{"model_portfolios":[{"model_portfolio_id":"MODEL_EXAMPLE","model_portfolio_version":"v1","display_name":"Example model","base_currency":"USD","risk_profile":"balanced","mandate_type":"discretionary","approval_status":"approved","effective_from":"2026-09-01","effective_to":"2026-09-01"}]}
```

Valid requests use the existing HTTP 202 ingestion receipt. If either example instead supplies
`effective_to="2026-08-31"`, the 422 `detail` entry has type `INVALID_EFFECTIVE_WINDOW`, message
`effective_to must be on or after effective_from.`, and field context `effective_to`. No accepted
source row or ingestion job is created. Omitting `effective_to` or supplying null remains valid.
Identical source upserts retain row identity and exact business values; valid end-date corrections
use the existing source upsert identity. Invalid corrections cannot replace the prior valid row.
This is source upsert behavior, separate from request-idempotency and durable job replay.

## Migration preflight and recovery

Migration `c184b2c3d545`, following `c183b2c3d544`, adds named checks on both owning tables:
`ck_model_portfolio_definition_effective_window` and
`ck_model_portfolio_target_effective_window`. It takes bounded exclusive locks on both tables,
then checks both before adding either constraint. Reversed retained rows refuse the deployment
with `MODEL_PORTFOLIO_INVALID_EFFECTIVE_WINDOW` and the affected table name. The failed transaction
preserves all source rows, their values and metadata, existing constraints, and the prior Alembic
version. Lock contention refuses after five seconds rather than bypassing preflight. Nullable
ends and equal-day records satisfy the database checks, including direct inserts and updates.

Before deployment, run this read-only inspection against the intended database using its approved
connection tooling; inspect both result sets even when the first is nonempty:

```sql
SELECT id, model_portfolio_id, model_portfolio_version, effective_from, effective_to,
       source_system, source_record_id, observed_at, quality_status
FROM model_portfolio_definitions WHERE effective_to < effective_from;
SELECT id, model_portfolio_id, model_portfolio_version, instrument_id, target_weight,
       effective_from, effective_to, source_system, source_record_id, observed_at, quality_status
FROM model_portfolio_targets WHERE effective_to < effective_from;
```

If either result is nonempty, stop promotion. Preserve the original rows and captured evidence
under the operator's existing governed custody, identify the source owner, and obtain an explicit
source disposition. Do not delete rows, swap dates, null the end, mark them inactive or silently
rewrite source values to make deployment pass. A separately authorized source correction requires
retaining the original evidence and using the supported source workflow; this migration performs
no correction or quarantine. Keep the prior release/schema until disposition is complete, then
repeat the inspection and upgrade. The exclusive locks fence concurrent old writers during the
actual preflight; an earlier read-only scan alone is not that fence.

From the repository root, with the intended `HOST_DATABASE_URL` already configured:

```powershell
python -m alembic current
python -m alembic upgrade head
```

```bash
python -m alembic current
python -m alembic upgrade head
```

Normal downgrade to `c183b2c3d544` removes only these two checks and preserves rows. It reopens the
old admission gap, so use it only within an approved rollback; it does not repair retained data.

## Validation and related ownership

From the repository root, run `make test-query-authority-db-contract` in PowerShell or Bash. The
native lane includes registered HTTP plus actual command/registry/persistence, fresh-session
PostgreSQL selection, and real Alembic previous-version refusal/upgrade/downgrade proofs. Job
bookkeeping and request replay lookup are explicit doubles in the HTTP cohort; no broker,
durable-job replay, trusted provider, process restart or capacity certification is claimed.

Both model families are covered by [Core #1165](https://github.com/sgajbi/lotus-core/issues/1165).
Broader model governance/version publication remains
[Platform #912](https://github.com/sgajbi/lotus-platform/issues/912); tenant isolation remains
[Core #798](https://github.com/sgajbi/lotus-core/issues/798); broader reference/source temporal
qualification remains [Core #458](https://github.com/sgajbi/lotus-core/issues/458). Other effective
window families retain their existing contracts and require their owning issue's assessment;
this fix does not convert half-open source-observation intervals or certify those families.
