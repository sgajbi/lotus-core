# Current Source Revaluation Amplification

## Objective

Remove redundant valuation replay created by current-business-date price and FX observations while
preserving effective-dated correction behavior.

## Finding

The exact-source 100,000-transaction daily profile accepted the complete input workload but failed
to drain within the fixed two-hour budget. At timeout, Core had created `135,982`
`valuation.snapshot.persisted` outbox events for `94,933` unique daily snapshots. PostgreSQL
reached `98.33%` runtime CPU, seven blocked sessions, and a position-timeseries p95 handoff latency
of `1,583.10s`.

The initial price and FX facts were current for the governed business date and arrived before any
positions existed. Both source handlers nevertheless staged durable replay. As positions became
visible, that replay reset already-correct position epochs and repeated valuation and derived-state
work. This was unnecessary because transaction processing already emits one valuation-readiness
fact for every later position mutation, and valuation reads the committed current price and FX
facts.

## Implemented Direction

1. `source_revaluation.py` owns one framework-neutral temporal scheduling policy for price and FX
   observations.
2. A current-date observation scans currently visible positions for immediate valuation but does
   not stage durable replay.
3. A current-date observation with no visible positions relies on the later transaction-owned
   valuation-readiness fact.
4. Backdated observations retain immediate visible-position jobs plus durable replay.
5. Future observations and observations received before a business-date horizon retain durable
   replay and defer the visible-position scan.
6. FX plans expose whether replay was actually staged rather than defaulting the evidence to true.

## Compatibility

Public APIs, persisted source-event schemas, Kafka topics, and position valuation formulas are
unchanged. The intentional internal behavior change removes redundant current-date replay only.
Backdated and future correction contracts remain unchanged.

## Validation

- `96` valuation-orchestrator unit tests passed.
- Focused Ruff lint and format checks passed.
- Focused MyPy passed.
- Architecture boundary, domain layer, application workflow policy, and infrastructure adapter
  guards passed.

The implementation commit is `4b8a4c772`. The prior failed certifying artifact is
`output/task-runs/20260716T095705Z-bank-day-load.json`. Fresh runtime evidence remains required
before issue `#795` can move to fixed-local.

## Documentation Decision

Repository context and the bank-day runbook change because the temporal replay invariant changed.
No public OpenAPI or authored wiki contract changes.
