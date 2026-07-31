# CR-1673: Carry-Forward Aggregation Epoch Convergence

## Scope

This review covers portfolio aggregation job eligibility and claim identity when one security
creates a portfolio-day job and another security later advances the collective portfolio epoch.
It is the bounded Core correction for GitHub issue #836.

## Finding

The isolated canonical seed proof on current main reached complete/current holdings, complete
reconciliation, 11/11 valued positions, and zero valuation work. Reporting remained `PENDING`
because nine weekend aggregation jobs stayed open at `target_epoch=0` after the portfolio's
authoritative source scope advanced to epoch one.

The existing source fence correctly refused to process those jobs at a stale target epoch. The
promotion path, however, depended on position-timeseries materialization staging the same
portfolio date again. A carry-forward portfolio day created by another security has no guarantee
of receiving that same-date restaging event. The result was durable, non-actionable work that
readiness correctly continued to expose.

Baseline evidence:

- command: `python scripts/validation/canonical_front_office_seed_proof.py --prebuild-images`
- artifact: `output/task-runs/20260731T115448683180Z-dff6ba7471ed-canonical-front-office-seed-proof.json`
- SHA-256: `d2b6b22d0c2cdd235df3720fbd652ec833c4f9c2e5bdbaa238b68cecfc9b5876`
- blockers: nine pending aggregation jobs and reporting readiness `PENDING`
- unaffected evidence: holdings/pricing/transactions `READY`, positions quality `COMPLETE`,
  11/11 valued, zero unvalued, and zero failed jobs

## Correction

`PortfolioAggregationRepository` now resolves the latest authoritative snapshot for every
security on or before the aggregation date without prematurely truncating the scope to the job's
stored target epoch. Eligibility still fails closed unless every selected snapshot has an equally
fresh position-timeseries materialization.

The claim update derives the maximum epoch across that complete authoritative scope. If it is
higher than the stored target, the same fenced update promotes `target_epoch` and increments
`source_revision` before returning the lease. Calculation and terminal writes therefore continue
to use a claim-owned, durable source identity; no current-epoch re-read or readiness bypass was
introduced.

## Same-Pattern Review

The review covered:

- higher-epoch supersession while a job is already claimed;
- delayed lower-epoch staging and source-revision advancement;
- same-epoch corrections and materialization freshness;
- cross-security carry-forward dates where the advancing security has no snapshot on the job day;
- a two-session source commit between eligible-target selection and the lease update;
- deterministic `FOR UPDATE SKIP LOCKED` claim ordering and terminal ownership checks.

The new PostgreSQL case models a Sunday job staged by one security at epoch zero and a second
security whose latest Friday snapshot is epoch one. The job is leased at epoch one with source
revision two and reaches `COMPLETE` only after both authoritative inputs are materialized.

Independent review identified a distinct terminal-state extension: a carry-forward date already
`COMPLETE` or `FAILED` before another security advances can also miss same-date restaging. Scanning
all historical terminal jobs from the hot claim loop would be unbounded, so that change is not
hidden inside this P0 repair. The bounded staging/rearm design and proof remain tracked under the
derived-state correctness acceptance of #714.

## Compatibility And Documentation Decision

The change preserves schema, migration, API, OpenAPI, event, topic, partition, calculation,
timeout, and readiness-threshold contracts. `UNKNOWN`, `PARTIAL`, `STALE`, blocked, and open-queue
postures remain fail closed. Repository engineering context changed because the durable job
identity rule changed. No wiki source changes are required: operator commands, public contracts,
and runtime topology are unchanged.

## Validation

- aggregation repository unit, integration, and generator repository suites: `52 passed`
- corrected isolated canonical proof: pending
- governed Workbench canonical validation: pending
- protected PR and exact-main evidence: pending
