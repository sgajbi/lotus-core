# RFC-083 Kafka Topic Naming and Event Taxonomy Standard

Date: `2026-03-19`

Status: `Implemented`

Owner: `lotus-core platform and service maintainers`

## 1. Purpose
Define the durable Kafka topic naming standard for `lotus-core`, document the canonical runtime topic taxonomy now implemented in code, and record the semantic rules that keep topic naming consistent going forward.

This RFC exists because the old topic vocabulary made the event graph harder to learn, review, operate, and extend than it needed to be. The runtime now uses the canonical names defined here; this document is the lasting standard and historical rationale for that rollout.

## 2. Problem Statement
The pre-RFC topic set evolved incrementally and mixed multiple naming grammars:

1. ingestion-state prefixes:
 - `transactions.raw.received`
 - `portfolios.raw.received`
 - `business_dates.raw.received`
2. persistence/result suffixes:
 - `transactions.persisted`
 - `market_prices.persisted`
3. calculator/result suffixes:
 - `transactions.cost.processed`
 - `cashflows.calculated`
 - `positions.valued`
4. orchestration command-style suffixes:
 - `valuation.job.requested`
 - `portfolio_day.aggregation.job.requested`
 - `portfolio_day.reconciliation.requested`
5. orchestration/finalization suffixes:
 - `portfolio_security_day.valuation.completed`
 - `portfolio_security_day.position_timeseries.completed`
 - `portfolio_day.aggregation.completed`

This creates four recurring problems:

1. similar names carry different semantics
 - `transactions.persisted`
 - `transactions.cost.processed`
 - `transaction_processing.ready`
2. command topics and fact topics are not clearly separated
3. topic names encode different dimensions inconsistently:
 - data stage
 - business action
 - technical artifact
 - orchestration intent
4. onboarding requires memorization instead of inference

The result is avoidable cognitive load for:
 - new engineers
 - incident responders
 - architecture reviewers
 - test authors
 - support operators trying to understand what stage a portfolio-day is in

## 3. Scope
This RFC covers:

1. Kafka topic naming grammar
2. event-type classification for topics
3. the implemented canonical runtime topic set
4. documentation, tooling, and governance requirements

This RFC does not cover:

1. Kafka broker architecture migration
 - example: ZooKeeper to KRaft
2. partition-count or replication-factor tuning
3. event payload schema redesign
4. replacing Kafka with another transport

## 4. Goals
1. Make topic meaning inferable from the name
2. Separate command-like topics from fact/event topics
3. Use one stable grammar across all services
4. Make the event graph easier to explain and debug
5. Prevent reintroduction of legacy or alias naming

## 4.1 Implementation Status
The canonical Kafka topic names defined in this RFC are implemented in:

- shared config and topic registry
- Kafka topic creation tooling
- service producers and consumers
- test fixtures and Docker-backed integration flows
- active feature and architecture documentation

Legacy aliases and compatibility-only runtime names are intentionally out of scope for the current implementation state. New work must use the canonical topic constants and canonical topic strings only.

## 5. Non-Goals
1. One-shot renaming of all topics in a single release
2. Changing business workflow semantics in the same RFC
3. Rewriting all historical test and support artifacts immediately

## 6. Current Topology Summary
`lotus-core` uses Kafka as an inter-service event bus. Services produce and consume events between ingestion, persistence, calculation, valuation, timeseries, aggregation, and reconciliation stages.

Representative topology from the current codebase:

1. `ingestion_service`
 - publishes raw inbound events
2. `persistence_service`
 - consumes raw topics and publishes persistence-complete events
3. calculator services
 - consume persistence outputs and publish calculator outputs
4. `pipeline_orchestrator_service`
 - publishes orchestration and control-stage events
5. valuation/timeseries/aggregation/reconciliation services
 - consume orchestration events and publish completion facts

Authoritative sources for the current topology:
 - [tools/kafka_setup.py](C:\Users\Sandeep\projects\lotus-core\tools\kafka_setup.py)
 - [config.py](C:\Users\Sandeep\projects\lotus-core\src\libs\portfolio-common\portfolio_common\config.py)
 - service `consumer_manager.py` files under `src/services/**`

## 7. Current Topic Inventory and Observed Problems

### 7.1 Ingestion and Persistence Layer
| Current Topic | Primary Meaning | Observed Problem |
| --- | --- | --- |
| `portfolios.raw.received` | inbound portfolio records | `raw_` prefix communicates stage, but not whether this is a command or fact |
| `transactions.raw.received` | inbound transaction records | same issue |
| `instruments` | inbound instrument records | inconsistent with `raw_*`; missing stage verb |
| `market_prices` | inbound market price records | inconsistent with `raw_*`; ambiguous whether inbound or persisted |
| `fx_rates` | inbound FX rate records | inconsistent with `raw_*` |
| `raw_business_dates` | inbound business dates | mixed style with raw-prefixed and non-prefixed peers |
| `transactions.persisted` | transactions persisted and available downstream | sounds similar to later processing-complete topics |
| `market_prices.persisted` | market prices persisted | clearer than `transactions.persisted`, but uses different grammar |

### 7.2 Calculation and Pipeline Layer
| Current Topic | Primary Meaning | Observed Problem |
| --- | --- | --- |
| `transactions.cost.processed` | transaction cost-processing output | too close to `transactions.persisted` and `transaction_processing.ready` |
| `transaction_processing.ready` | transaction-scoped readiness gate after cost and cashflow prerequisites are both seen | name overlaps with transaction-level processed/completed wording and overstates portfolio-day scope |
| `cashflows.calculated` | cashflow results available | clearer, but grammar differs from persisted/completed topics |
| `valuation.snapshot.persisted` | valuation snapshot artifact persisted | artifact-oriented naming, not event-oriented |
| `positions.valued` | positions valued | narrower than snapshot artifact; meaning may overlap with snapshot-persisted event |

### 7.3 Orchestration and Day-Level Layer
| Current Topic | Primary Meaning | Observed Problem |
| --- | --- | --- |
| `portfolio_security_day.valuation.ready` | readiness fact that a portfolio-security day can be scheduled for valuation | name says `portfolio_day`, but payload is really portfolio-security-day scoped |
| `valuation.job.requested` | valuation work should be scheduled/executed | command-like topic using a different suffix from `requested` |
| `timeseries.position.generated` | timeseries generation result or signal | ambiguous whether command or fact |
| `portfolio_day.aggregation.job.requested` | aggregation work should be executed | command-style topic, different grammar from `requested` |
| `portfolio_security_day.valuation.completed` | valuation day finished | completion grammar |
| `portfolio_security_day.position_timeseries.completed` | timeseries day finished | completion grammar |
| `portfolio_day.aggregation.completed` | aggregation day finished | completion grammar |
| `portfolio_day.reconciliation.requested` | reconciliation requested | command grammar |
| `portfolio_day.reconciliation.completed` | reconciliation finished | completion grammar |
| `portfolio_day.controls.evaluated` | support/control evaluation finished | fact grammar, but name style differs from other day-level events |

### 7.4 Recovery and DLQ Layer
| Current Topic | Primary Meaning | Observed Problem |
| --- | --- | --- |
| `transactions.reprocessing.requested` | replay or reprocessing requested | command grammar, but plural/domain placement differs from other command topics |
| `dlq.persistence_service` | terminal-failure dead-letter topic | service-specific DLQ naming is workable, but not standardized |

### 7.5 Exact Current Producer and Consumer Matrix
The table below captures the current runtime topology as implemented in service producers, consumer managers, and shared replay tooling. It intentionally distinguishes active paths from configured-but-inactive topic names.

| Current Topic | Current Producer(s) | Current Consumer(s) / Group(s) | Current Semantic Reality | Notes |
| --- | --- | --- | --- | --- |
| `portfolios.raw.received` | `ingestion_service` | `persistence_service` / `persistence_group_portfolios` | inbound raw fact | Active ingress path |
| `transactions.raw.received` | `ingestion_service` | `persistence_service` / `persistence_group_transactions` | inbound raw fact | Active ingress path |
| `instruments` | `ingestion_service`; `cost_calculator_service` side-effect publication | `persistence_service` / `persistence_group_instruments` | mixed-source instrument fact stream | Naming is especially unclear because a non-ingestion calculator also publishes here |
| `market_prices` | `ingestion_service` | `persistence_service` / `persistence_group_market_prices` | inbound raw fact | Active ingress path |
| `fx_rates` | `ingestion_service` | `persistence_service` / `persistence_group_fx_rates` | inbound raw fact | Active ingress path |
| `raw_business_dates` | `ingestion_service` | `persistence_service` / `persistence_group_business_dates` | inbound raw fact | Active ingress path |
| `transactions.persisted` | `persistence_service`; shared replay tooling in `reprocessing_repository` | `cost_calculator_service` / `cost_calculator_group`; `cashflow_calculator_service` / `cashflow_calculator_group` | transactions persisted and replay-fed downstream | This is the first member of the confusing transaction-stage trio |
| `transactions.cost.processed` | `cost_calculator_service`; `position_calculator_service` back-dated replay outbox | `cashflow_calculator_service` / `cashflow_calculator_group_replay`; `position_calculator_service` / `position_calculator_group_replay`; `pipeline_orchestrator_service` / `pipeline_orchestrator_processed_txn_group` | cost-processed transaction fact plus replay carrier | This topic currently carries both normal calculator output and replay traffic |
| `transaction_processing.ready` | `pipeline_orchestrator_service` | `position_calculator_service` / `position_calculator_group_gated` | transaction-scoped readiness fact | Semantically very different from the two similarly named transaction topics above |
| `cashflows.calculated` | `cashflow_calculator_service` | `pipeline_orchestrator_service` / `pipeline_orchestrator_cashflow_group` | calculator output fact | Active stage-completion input to orchestrator |
| `portfolio_security_day.valuation.ready` | `pipeline_orchestrator_service` | `valuation_orchestrator_service` / `valuation_orchestrator_group_readiness` | readiness fact that causes durable valuation-job upsert | Name reads like state and the payload is actually portfolio-security-day scoped |
| `market_prices.persisted` | `persistence_service` | `valuation_orchestrator_service` / `valuation_orchestrator_group_price_events` | persistence fact | Clearer grammar than many peers |
| `valuation.job.requested` | `valuation_orchestrator_service` scheduler | `position_valuation_calculator` / `position_valuation_worker_group` | worker dispatch request | This is the real valuation job command topic |
| `valuation.snapshot.persisted` | `position_valuation_calculator` | `timeseries_generator_service` / `timeseries_generator_group_positions` | persisted valuation artifact fact | Artifact-oriented name rather than event-oriented name |
| `portfolio_security_day.valuation.completed` | `position_valuation_calculator` | no primary direct Kafka consumer in current runtime; compatibility parsing remains in `timeseries_generator_service` | stage completion fact | Still has compatibility meaning even though the primary fan-out path uses `valuation.snapshot.persisted` |
| `portfolio_security_day.position_timeseries.completed` | `timeseries_generator_service` | no direct Kafka consumer found in current runtime | stage completion fact | Current runtime appears to rely on DB/scheduler flow rather than Kafka chaining here |
| `portfolio_day.aggregation.job.requested` | `portfolio_aggregation_service` scheduler | `portfolio_aggregation_service` / `portfolio_aggregation_group` | worker dispatch request | Producer and consumer live in the same service boundary |
| `portfolio_day.aggregation.completed` | `portfolio_aggregation_service` | `pipeline_orchestrator_service` / `pipeline_orchestrator_portfolio_aggregation_group` | stage completion fact | Active downstream trigger to reconciliation |
| `portfolio_day.reconciliation.requested` | `pipeline_orchestrator_service` | `financial_reconciliation_service` / `portfolio_day.reconciliation.requested_group` | orchestration request | Clear command topic, but grammar differs from `valuation.job.requested` and `portfolio_security_day.valuation.ready` |
| `portfolio_day.reconciliation.completed` | `financial_reconciliation_service` | `pipeline_orchestrator_service` / `pipeline_orchestrator_reconciliation_completion_group` | stage completion fact | Active control-stage input |
| `portfolio_day.controls.evaluated` | `pipeline_orchestrator_service` | no direct Kafka consumer found in current runtime | support/control evaluation fact | Useful topic, but currently appears to terminate rather than feed another Kafka stage |
| `transactions.reprocessing.requested` | `ingestion_service` retry/reprocess paths | `cost_calculator_service` / `cost_reprocessing_group` | replay command | Current name is understandable but inconsistent with broader command grammar |
| `dlq.persistence_service` | shared base-consumer DLQ path across multiple services | consumed operationally, not by an app consumer group | terminal failure sink | Service-named DLQ is workable but not standardized |
| `positions.valued` | no active producer found in current runtime | no active consumer found in current runtime | configured legacy topic constant | Present in config and topic setup, but not part of the active graph reviewed here |
| `timeseries.position.generated` | no active producer found in current runtime | no active consumer found in current runtime | configured legacy topic constant | Present in config and topic setup, but appears superseded by `portfolio_security_day.position_timeseries.completed` |
| `timeseries.portfolio.generated` | no active producer found in current runtime | no active consumer found in current runtime | configured legacy topic constant | Defined in config, but no active runtime path was found |

## 8. Design Principles
The new standard should follow these principles:

1. domain-first naming
 - start with the business entity or workflow domain
2. one topic, one semantic type
 - either command/request or fact/event
3. explicit event tense
 - commands end in `requested`
 - facts end in a past-tense or state-change word such as `persisted`, `calculated`, `completed`, `evaluated`
4. avoid overloaded “completed”
 - do not use `completed` when the more precise state is `persisted`, `scheduled`, or `evaluated`
5. avoid ambiguous stage adjectives like `raw` unless they are part of a standard hierarchy
6. prefer singular workflow nouns over ad hoc word bundles
7. keep the terminal segment small and semantic
 - qualifiers belong in their own segment
 - example: `transactions.cost.processed`, not `transactions.cost_processed`
8. model scope honestly
 - if an event is portfolio-security-day scoped, do not name it `portfolio_day.*`
9. distinguish readiness facts from dispatch requests
 - `*.ready` means prerequisites are satisfied
 - `*.requested` means another component is being asked to do work

## 9. Proposed Naming Standard

### 9.1 Topic Grammar
All new Kafka topics should follow one of these forms:

1. fact/event topics:
 - `<domain>.<entity>.<event>`
2. command/request topics:
 - `<domain>.<entity>.requested`
3. readiness/state facts:
 - `<domain>.<entity>.ready`
 - `<domain>.<entity>.completed`
3. dead-letter topics:
 - `dlq.<consumer_group_or_service>`

Optional sub-entity path:
 - `<domain>.<entity>.<subentity>.<event>`

Examples:
 - `transactions.raw.received`
 - `transactions.persisted`
 - `transactions.cost.processed`
 - `transaction_processing.ready`
 - `portfolio_security_day.valuation.ready`
 - `valuation.job.requested`
 - `portfolio_day.controls.evaluated`
 - `valuation.snapshot.persisted`
 - `timeseries.position.completed`
 - `portfolio_day.reconciliation.requested`
 - `dlq.persistence_service`

### 9.2 Semantic Vocabulary
Allowed terminal event words should be intentionally small:

Command/request vocabulary:
 - `requested`

Fact/event vocabulary:
 - `received`
 - `persisted`
 - `calculated`
 - `processed`
 - `ready`
 - `scheduled`
 - `completed`
 - `evaluated`
 - `generated`

Use the narrowest correct word:
 - if DB durability is the key meaning, use `persisted`
 - if prerequisites are satisfied and another component may schedule later, use `ready`
 - if an orchestrator or scheduler is asking for work, use `requested`
 - if a stage has fully converged, use `completed`

## 10. Proposed Current-to-Target Mapping

### 10.1 Ingestion Inputs
| Current | Proposed |
| --- | --- |
| `portfolios.raw.received` | `portfolios.raw.received` |
| `transactions.raw.received` | `transactions.raw.received` |
| `instruments` | `instruments.received` |
| `market_prices` | `market_prices.raw.received` |
| `fx_rates` | `fx_rates.raw.received` |
| `raw_business_dates` | `business_dates.raw.received` |

`instruments` is intentionally not mapped to `instruments.raw.received` because the current topic is not purely external ingress. It already carries derived instrument events emitted by `cost_calculator_service`.

### 10.2 Persistence Outputs
| Current | Proposed |
| --- | --- |
| `transactions.persisted` | `transactions.persisted` |
| `market_prices.persisted` | `market_prices.persisted` |

Future optional normalization if persistence events are added:
 - `portfolios.persisted`
 - `instruments.persisted`
 - `fx_rates.persisted`
 - `business_dates.persisted`

### 10.3 Calculator Outputs
| Current | Proposed |
| --- | --- |
| `transactions.cost.processed` | `transactions.cost.processed` |
| `transaction_processing.ready` | `transaction_processing.ready` |
| `cashflows.calculated` | `cashflows.calculated` |
| `positions.valued` | `positions.valued` |
| `valuation.snapshot.persisted` | `valuation.snapshot.persisted` |

### 10.4 Orchestration and Day-Level Topics
| Current | Proposed |
| --- | --- |
| `portfolio_security_day.valuation.ready` | `portfolio_security_day.valuation.ready` |
| `valuation.job.requested` | `valuation.job.requested` |
| `timeseries.position.generated` | `timeseries.position.generated` |
| `portfolio_day.aggregation.job.requested` | `portfolio_day.aggregation.job.requested` |
| `portfolio_security_day.valuation.completed` | `portfolio_security_day.valuation.completed` |
| `portfolio_security_day.position_timeseries.completed` | `portfolio_security_day.position_timeseries.completed` |
| `portfolio_day.aggregation.completed` | `portfolio_day.aggregation.completed` |
| `portfolio_day.reconciliation.requested` | `portfolio_day.reconciliation.requested` |
| `portfolio_day.reconciliation.completed` | `portfolio_day.reconciliation.completed` |
| `portfolio_day.controls.evaluated` | `portfolio_day.controls.evaluated` |

### 10.5 Recovery and DLQ
| Current | Proposed |
| --- | --- |
| `transactions.reprocessing.requested` | `transactions.reprocessing.requested` |
| `dlq.persistence_service` | `dlq.persistence_service` |

## 11. Naming Decision Notes

### 11.1 Why `requested` for command topics
Current command-like topics use:
 - `required`
 - `requested`
 - `ready_for_valuation`

This is inconsistent.

`requested` is preferred because it communicates:
 - this is an intent for another component to act
 - the action may still fail, be retried, or be deduplicated

`required` reads more like a state assertion than an orchestration event.

`ready` is intentionally different:
 - it means prerequisites are satisfied
 - another component may now schedule or dispatch work
 - it should not be used for direct worker commands

### 11.2 Why not put `raw_` at the front anymore
The `raw_` prefix is short, but it does not tell us:
 - who produced the event
 - whether it is a command or fact
 - which stage is downstream

`transactions.raw.received` is longer, but much clearer.

Exception:
 - do not force `raw` into a canonical name if the current or future stream is intentionally mixed-source
 - `instruments.received` is preferable to `instruments.raw.received` while the topic carries both ingress and derived events

### 11.3 Why not use `completed` everywhere
`completed` is too broad.

Examples:
 - DB write completion is not the same as end-to-end workflow completion
 - scheduler request publication is not the same as final business convergence

Using `persisted`, `requested`, `evaluated`, and `completed` distinctly makes the event graph easier to reason about.

### 11.4 Why scope honesty matters
The current runtime has both:
 - portfolio-day events
 - portfolio-security-day events
 - transaction-scoped readiness events

The canonical names must reflect that reality.

Examples:
 - `transaction_processing.ready` is transaction-scoped
 - `portfolio_security_day.valuation.ready` is portfolio-security-day scoped
 - `portfolio_day.aggregation.completed` is portfolio-day scoped

Blurring those scopes in the name makes operations, replay, and support reasoning harder.

### 11.5 Why replay needs explicit policy
The current runtime uses replay in three distinct ways:

1. replay request:
 - `transactions.reprocessing.requested`
2. replay republish to a persisted-output topic:
 - `transactions.persisted`
3. epoch-bumped replay republish to a processed-output topic:
 - `transactions.cost.processed`

RFC-083 treats replay as part of naming governance, not an implementation footnote.

Canonical policy should be explicit:
 - replay may re-emit the same business fact on the same canonical topic when the downstream semantic meaning is unchanged
 - replay should not force a separate replay topic unless consumers need distinct routing semantics
 - when replay emits onto the same canonical topic, payload metadata such as epoch and lineage must carry the replay distinction

## 12. Service-by-Service Interpretation Under the New Standard

### 12.1 Ingestion to Persistence
1. `ingestion_service`
 - publishes `*.raw.received`
2. `persistence_service`
 - consumes `*.raw.received`
 - publishes `*.persisted`
3. mixed-source exception
 - instrument traffic should remain truthfully named until ingress and derived instrument publication are split or intentionally formalized

### 12.2 Transaction Calculator Chain
1. `cost_calculator_service`
 - consumes `transactions.persisted`
 - publishes `transactions.cost.processed`
2. `cashflow_calculator_service`
 - consumes transaction outputs
 - publishes `cashflows.calculated`
3. `pipeline_orchestrator_service`
 - consumes `transactions.cost.processed` and `cashflows.calculated`
 - publishes `transaction_processing.ready`
4. `position_calculator_service`
 - consumes `transaction_processing.ready`
 - may republish replay traffic onto `transactions.cost.processed` under epoch fencing

### 12.3 Valuation and Day-Level Chain
1. `pipeline_orchestrator_service`
 - publishes `portfolio_security_day.valuation.ready`
 - publishes `portfolio_day.reconciliation.requested`
 - publishes `portfolio_day.controls.evaluated`
2. `valuation_orchestrator_service`
 - consumes `portfolio_security_day.valuation.ready`
 - publishes `valuation.job.requested`
3. `position_valuation_calculator`
 - consumes `valuation.job.requested`
 - publishes `valuation.snapshot.persisted`
 - publishes `portfolio_security_day.valuation.completed`
4. `timeseries_generator_service`
 - consumes `valuation.snapshot.persisted`
 - publishes `portfolio_security_day.position_timeseries.completed`
5. `portfolio_aggregation_service`
 - consumes `portfolio_day.aggregation.job.requested`
 - publishes `portfolio_day.aggregation.completed`
6. `financial_reconciliation_service`
 - consumes `portfolio_day.reconciliation.requested`
 - publishes `portfolio_day.reconciliation.completed`

## 13. Migration Strategy
This RFC explicitly rejects a big-bang rename.

Migration should happen in phases:

### Phase 0: Governance and Documentation
1. approve the naming standard
2. document current-to-target mappings
3. update architecture diagrams and onboarding docs

### Phase 1: Canonical Alias Layer
1. add canonical topic constants alongside legacy ones
2. support dual constants in `portfolio_common.config`
3. leave runtime behavior unchanged initially
4. mark configured legacy topics with explicit status:
 - active
 - compatibility-only
 - deprecated
 - removable

### Phase 2: Producer Dual-Publish or Topic Alias Strategy
Two migration options exist:

Option A: dual publish temporarily
 - producer writes old and new topic names
 - consumers can migrate independently

Option B: config-mapped alias topic rollout
 - code moves to canonical constant names
 - environment config still points to legacy runtime topic names
 - physical topic migration comes later

Preferred first step:
 - Option B

Reason:
 - much lower operational risk
 - no duplicate event traffic
 - lets code and docs converge before Kafka infrastructure renames

### Phase 3: Consumer Migration
1. move consumers to canonical topic constants
2. verify no services still depend on legacy names
3. verify replay and DLQ tooling compatibility
4. verify readiness facts and dispatch requests are still distinct in routing and dashboards

### Phase 4: Runtime Topic Rename
1. create physical canonical topics
2. migrate producers and consumers in controlled order
3. retire legacy topics
4. keep replay tooling aware of historical topic names if needed

## 14. Compatibility and Risk

### 14.1 Risks
1. producer/consumer mismatch during migration
2. replay tooling and DLQ audit filters breaking on renamed topics
3. support-plane dashboards or scripts hardcoding topic names
4. test fixtures assuming legacy names
5. incorrect scope normalization
 - transaction, portfolio-day, and portfolio-security-day events accidentally flattened into one namespace
6. mixed-source topic renames becoming semantically false
 - especially `instruments`

### 14.2 Mitigations
1. canonical constants before physical rename
2. topic inventory tests
3. replay tooling accepting both legacy and canonical names during migration
4. staged rollout by topic family rather than by whole system
5. explicit event-scope review for every rename
6. do not rename mixed-source topics into a narrower semantic name without first splitting the stream

## 15. Tooling and Governance Requirements
To make the standard durable, `lotus-core` should add:

1. topic taxonomy documentation generated from config/constants
2. a contract guard ensuring new topics follow the approved naming regex
3. service ownership mapping for each topic:
 - producer(s)
 - consumer group(s)
 - DLQ policy
4. support/runbook documentation for canonical topic meanings
5. lifecycle governance for configured legacy topics
 - every topic in config and topic bootstrap must be classified as `active`, `compatibility-only`, or `deprecated`
 - deprecated topics must have an owner and removal criteria

Recommended topic-name regex:

`^[a-z0-9]+(\\.[a-z0-9_]+)+$`

With a semantic rule:
 - final segment must be one of approved verbs/states
 - qualifiers must occupy their own segment, not be fused into the terminal segment

## 16. Rollout Priority
The first renames worth doing are the most confusing ones:

Priority 1:
1. `transactions.persisted` -> `transactions.persisted`
2. `transactions.cost.processed` -> `transactions.cost.processed`
3. `transaction_processing.ready` -> `transaction_processing.ready`

Priority 2:
1. `portfolio_security_day.valuation.ready` -> `portfolio_security_day.valuation.ready`
2. `valuation.job.requested` -> `valuation.job.requested`
3. `portfolio_day.aggregation.job.requested` -> `portfolio_day.aggregation.job.requested`

Priority 3:
1. resolve the mixed-source `instruments` topic naming
2. normalize DLQ topic naming
3. normalize snapshot/timeseries artifact naming and compatibility topics

## 17. Alternatives Considered

### Alternative A: keep names as-is and improve docs only
Rejected as the long-term answer.

Reason:
 - documentation helps, but naming confusion remains in code, tests, dashboards, and incident response

### Alternative B: rename everything immediately
Rejected.

Reason:
 - too risky operationally
 - unnecessary churn

### Alternative C: only rename the worst transaction-completion trio
Viable as a narrow first slice, but insufficient as a full standard.

## 18. Open Questions
1. Should command topics always include the workflow owner:
 - `portfolio_day.valuation.requested`
 - or can some remain shorter:
 - `valuation.requested`
2. Should snapshot artifact topics be normalized around `valuation.snapshot.*` or `positions.snapshot.*`?
3. Should DLQ topics be service-based:
 - `dlq.persistence_service`
or consumer-group-based:
 - `dlq.persistence_group_transactions`
4. Do we want a single repository-level event catalog generated from code?
5. Should `instruments` be split into separate ingress and derived-instrument topics, or remain intentionally mixed with a broader canonical name?
6. Should replay continue to re-emit the same business fact on the same canonical topic by policy, or do we want dedicated replay topics for some stage families?

## 19. Recommended Decision
Approve the naming standard and semantic taxonomy in this RFC.

Execution recommendation:
1. adopt canonical constants first
2. do not physically rename Kafka topics in the same slice
3. migrate the most confusing transaction, readiness, and dispatch topics first
4. add a guardrail so new topics cannot extend the old inconsistency
5. require explicit scope and replay classification for every future topic

## 20. Exit Criteria
This RFC can move from `Draft` to `Approved` when:

1. the naming grammar is accepted
2. the current-to-target mapping is accepted
3. the migration strategy is accepted

This RFC can move from `Approved` to `Implemented` when:

1. canonical topic constants exist for the approved taxonomy
2. at least the Priority 1 topics are migrated in code
3. topic naming governance exists in CI or repository tooling
4. support and replay tooling are updated for canonical topic semantics
5. configured legacy topics have explicit deprecation status and removal criteria
