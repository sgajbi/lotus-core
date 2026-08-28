# Kafka Contract: Position Processing

The cost, cashflow, and position modules all run inside the unified `portfolio_transaction_processing_service`
deployment. It is a Kafka worker: it exposes no business REST API, only operational HTTP endpoints
for health, metrics, and build identity.

## 1. Health & Metrics API

* **Container port:** `8085`
* **Host default:** `http://localhost:8090` (override with `LOTUS_TRANSACTION_PROCESSING_HOST_PORT`)

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/health/live` | A liveness probe to confirm the service process is running. Returns `{"status": "alive"}`. |
| `GET` | `/health/ready` | A readiness probe over **three** dependencies — `db`, `kafka`, and `worker_runtime` (declared in `app/web.py`). Returns `{"status": "ready"}` on success or `503 Service Unavailable` on failure, with per-dependency detail in the body. A 503 is not necessarily a database problem: read the body to see which dependency failed. |
| `GET` | `/metrics` | Exposes performance and application metrics in Prometheus format. |
| `GET` | `/version` | Returns the build identity of the running image. |

## 2. Kafka Interface

Position processing has no Kafka topic of its own. It is one of three effects — cost, cashflow, and
position — applied inside a single atomic use case in the unified runtime, so there is no separate
position work queue to subscribe to or to measure lag on.

### 2.1. Consumer

The unified deployment builds five consumers, listed in full in
[the transaction-processing Kafka contract](../cost_calculator/02_API_Specification_Cost_Calculator.md#21-consumers).
**All five can drive position effects** — two directly, three by staging work that reaches the
atomic use case later:

| Topic | Consumer group | Drives position effects |
| --- | --- | --- |
| `transactions.persisted` | `portfolio_transaction_processing_group` | Directly, for newly persisted transactions. |
| `transactions.reprocessing.requested` | `portfolio_transaction_replay_request_group` | Directly, replaying an affected key after a back-dated correction. |
| `corporate_action.manifest.received` | `corporate_action_manifest_group` | Indirectly — governed corporate actions. |
| `fixed_income.book_cost.authority.received` | `fixed_income_book_cost_authority_group` | Indirectly — fixed-income book-cost corrections. |
| `fixed_income.book_cost.disposal_replay.requested` | `fixed_income_book_cost_correction_replay_group` | Indirectly — the second hop of that correction. |

The three indirect paths are the ones that surprise operators, because the two direct groups can be
completely current while position state is wrong.

**Corporate actions.** For a governed corporate-action child, `TransactionProcessingConsumer` routes
the arrival and returns *without financial mutation*, logging `Corporate-action child intake
completed without financial mutation.` The position effect happens later: the manifest makes the
durable release eligible, and `CorporateActionReleaseWorker` invokes `ProcessTransactionUseCase` for
each member.

**Fixed-income corrections.** This is a two-hop path.
`FixedIncomeBookCostAuthorityConsumer` handles an authority event and its unit of work stages
`fixed_income.book_cost.disposal_replay.requested`. `FixedIncomeBookCostCorrectionReplayConsumer`
then consumes that and invokes `ReplayBookedTransactionUseCase`, which republishes the canonical
transaction so cost and position are reprocessed atomically. A stall on *either* group leaves the
corrected cost basis unapplied.

So a stall on any of the three indirect groups produces the same symptom: position state that is
silently wrong while the two direct groups show no lag at all.

The service does **not** consume `transactions.cost.processed`. That topic is an outbound
compatibility event, described below; tracing position lag through it leads to a self-loop that does
not exist.

### 2.2. Producer

#### Topic: `transactions.cost.processed`

* **Purpose:** Records each processed transaction as a `ProcessedTransactionPersisted` event.
  `TransactionalCostProcessingEffectStager.stage_processed_transactions`
  (`app/infrastructure/cost_basis/effect_staging.py`) stages one outbox row per transaction inside
  the same unit of work that persists the cost, cashflow, and position effects, so the event cannot
  be emitted for work that did not commit. It is staged for every processed transaction, not only
  during reprocessing.
* **Consumer:** none at runtime. The event-supportability contract records this family with
  `consumer_services=()` and `runtime_active=False`; it is staged as a compatibility event, not a
  work queue. Position effects reach the runtime through `transactions.persisted` and
  `transactions.reprocessing.requested` — two of its five subscriptions, not the whole contract — so
  do not trace replay or lag through a self-loop on this topic. Position effects are applied inside
  the atomic transaction-processing use case before this event is staged.
* **Key:** `portfolio_id`
* **Payload (`TransactionEvent`):** The event business payload of the processed transaction,
  carrying its `epoch`. Reprocessing raises the epoch for the affected key, so events staged after a
  back-dated correction carry the higher value. Epoch fencing is enforced by the epoch-aware query
  and derived-state reads against durable state, not by consuming this topic — it has no runtime
  consumer.
    ```json
    {
        "transaction_id": "HISTORICAL_TXN_001",
        // ... all other fields
        "epoch": 1 // The epoch has been incremented
    }
    ```