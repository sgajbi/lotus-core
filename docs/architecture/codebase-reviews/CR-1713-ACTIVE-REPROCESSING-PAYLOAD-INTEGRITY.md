# CR-1713 Active Reprocessing Payload Integrity

Date: 2026-08-26

Status: Fixed-local candidate; protected PR review, exact-head CI, exact-main validation, issue QA,
wiki publication, and branch/worktree hygiene remain pending.

Issue: #1038

## Finding

Valid repository writers now validate Reset and FX effective-dated replay inputs, but malformed
pending rows written by an earlier release or an out-of-band path could remain durable. SQL date
and timestamp casts used during staging and coalescing would then abort the transaction before the
worker could terminalize the poisoned row, risking repeated queue-wide loss of progress.

## Financial And Temporal Invariant

Every active Reset or FX replay row must have safely extractable, string-typed replay identity and
temporal fields before SQL ordering or coalescing uses it. The application remains authoritative
for ISO temporal grammar. Deployment must not invent missing dates,
timestamps, hashes, or identities. Malformed pending work becomes attributable terminal evidence;
valid work and terminal history remain unchanged. A worker must not remain active during the
cutover, and future malformed active work must fail at the persistence boundary.

## Design

1. Forward migration `c162b2c3d529` takes a five-second-bounded exclusive table lock, refuses to
   run while any row is `PROCESSING`, and preflights relevant active payload text for JSONB-safe
   extraction before any JSON field extraction. Legacy literal-SQL NUL rows receive an actionable
   count and recovery hint rather than a driver-level Unicode error, while harmless literal escape
   text remains accepted.
2. It quarantines malformed pending FX and security Reset rows as `FAILED`, retaining the original
   payload and recording separate bounded row counts in PostgreSQL migration notices. While the
   exclusive lock is held, the immutable migration snapshots Python `fromisoformat` grammar into a
   transaction-local id set so PostgreSQL-only dates such as `infinity` are quarantined without a
   hand-written SQL grammar.
3. The model and migration declare one database CHECK constraint for `PENDING` and `PROCESSING`
   Reset/FX work. It uses a guarded CASE to require JSONB-safe extraction, JSON string types,
   nonblank normalized identities, database-representable dates, and, for FX, a normalized string
   content hash plus a database-representable, explicitly zoned `generated_at`. Python
   `fromisoformat` remains the single temporal-grammar authority, avoiding a divergent parser copied
   into SQL.
4. Terminal rows are intentionally outside the constraint so historical evidence is not rewritten
   or made undeployable by a newly introduced active-work contract.
5. Downgrade removes only the constraint. Quarantine is not reversed because restoring malformed
   work to the active queue would recreate the operational wedge.

## Same-Pattern Review

The review covered both temporal replay job families and every repository SQL writer to
`reprocessing_jobs.payload`. Reset and FX staging already validate their typed inputs; generic
creation routes Reset work through the governed staging method, and stale FX recovery uses the
typed replay validator introduced under #1032. The durable database constraint closes legacy,
restore, migration, and out-of-band active-write paths without duplicating validation across every
consumer. This CHECK is authoritative for post-cutover database representability and scalar types.
Application validation is authoritative for temporal grammar. Existing runtime quarantine remains
required for grammar-invalid predecessor, restore, migration-order, and out-of-band states, and its
behavior is proved separately rather than treated as reachable through ordinary current writers.
FX staging now locks matching predecessor rows, applies the same Python validator before any SQL
cast or `ON CONFLICT`, and terminalizes invalid evidence without laundering its boundary. Replay
text validation rejects padded values rather than silently changing durable identity.

The proposed S5 JSON-to-JSONB rewrite was not implemented. The initial probe bound escaped JSON
text through a parameter and observed rejection, but that evidence did not cover direct SQL literal
input; PostgreSQL 16.14 can persist the latter in a `json` column and fail only when `->>` extracts
the affected value. Review correctly exposed that population error. The migration now asks
PostgreSQL whether each relevant active `payload::text` is valid JSONB before extraction. That
tracks the actual extraction boundary without falsely rejecting harmless literal escape text,
while the active-row CHECK makes future unsafe active work unrepresentable. This closes the
queue-safety objective without changing JSON key ordering or duplicate-key behavior. The corrected
evidence is recorded on #1038.

## Meaningful Proof

- Unit migration proof pins the linear revision, drain/lock contract, both quarantine families,
  Python-owned temporal classification, type-level count capture, reversible constraint operations,
  normalization, and timezone-presence predicates.
- Model proof prevents ORM/schema drift by requiring the named constraint.
- Critical-lifecycle repository proof asserts that missing, database-unrepresentable, and
  non-string FX payload shapes fail at commit with the named CHECK constraint and leave no durable
  queue row. One shared predecessor-schema fixture temporarily removes and reliably restores that
  constraint around legacy-state tests, proving claim-time terminalization and valid-replay staging
  quarantine remain operational recovery defenses without duplicating schema manipulation.
- Real PostgreSQL migration proof seeds malformed FX and security rows plus valid pending work,
  seeds the literal-SQL legacy NUL path and harmless literal escape text, verifies only the unsafe
  row produces an actionable preflight failure, quarantines non-string, padded, and
  Python-grammar-invalid identity/temporal evidence, preserves application-accepted temporal
  spellings including an offset with seconds, verifies exact terminal reasons and valid-row
  preservation, rejects future non-string active writes, and proves downgrade/reapply behavior
  inside a rollback-owned test transaction.
- Final-head local evidence: focused migration/model/repository proofs passed, including the
  isolated real-PostgreSQL migration counterexample (drain, exact audit counts, quarantine,
  valid-row preservation, malformed-write rejection, downgrade, and reapply) and the affected
  real-PostgreSQL reprocessing repository tests. `make lint` passed its financial-integrity,
  architecture, security, contract, and governance gates; MyPy passed across 325 source files;
  the changed wiki page passed the professional-quality audit and source/publication check. The
  final `make test-critical-lifecycle-db` run at this head passed **64 selected tests** with 1,129
  deselected in 393.89 seconds, including predecessor-schema recovery cases in the shared
  reprocessing-job repository suite. The only warning is an unrelated deprecation assertion in
  ingestion transaction-lifecycle coverage.

## Compatibility And Scope

The JSON payload type, key-order and duplicate-key behavior, API/OpenAPI, events, Kafka, financial
calculations, dependencies, images, and deployment topology are unchanged. Malformed pending work
intentionally changes to `FAILED` during migration; new malformed active Reset/FX writes are
rejected. Wiki operations truth, the database schema catalog, and repository context document the
cutover and recovery boundary. Existing backend delivery and codebase-review skills already require
population-wide proof before generalizing from one writer, so no skill change is justified.

## Remaining Closure

Keep #1038 open until the corrected S5 implementation receives a current-head review verdict, the
protected PR receives merge authority, exact-head and exact-main gates pass, wiki source is
published with parity, and branch/worktree hygiene is verified.
