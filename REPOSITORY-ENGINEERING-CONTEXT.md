# Repository Engineering Context

This is the repository-local engineering context for `lotus-core`. It describes current
ownership, architecture, invariants, task routes, commands, and completion evidence. Active work
and PR status belong in GitHub; historical delivery belongs in RFC and review evidence.

Read [AGENTS.md](AGENTS.md), the Platform
[quickstart](https://github.com/sgajbi/lotus-platform/blob/main/context/LOTUS-QUICKSTART-CONTEXT.md),
and this file first. Then use the Platform
[skill routing map](https://github.com/sgajbi/lotus-platform/blob/main/context/LOTUS-SKILL-ROUTING-MAP.md)
and the task routes below to load only relevant specialist context.

## Repository Role

### Financial-effect epoch binding practice

Combined transaction processing binds an unversioned financial-effect transaction to the
authoritative locked epoch returned by its materialized portfolio/security position before
cashflow idempotency, calculation and readiness registration. Explicit epochs and rebuilt source
epochs retain their existing fences, including nonretryable stale cashflow rejection. Unversioned
effects without lock evidence or materialization fail closed in the unit of work. A raw semantic
duplicate is suppressed before position processing. Ordinary first-CLAIMED unversioned REPAIR
requires scoped locked canonical source and full original payload fingerprint equality before
costs; only then may native position rebuilding resolve an already-materialized input. Existing
correction and repair-delivery admissions retain their own authority. Canonical DB replay retains
the source epoch, including None; application controls do not certify the registered HTTP path.
Never guess or rewrite a source epoch, or default accepted current-epoch effects to zero
or query mutable latest state to replace their source cut.

Ordinary coalesced work retains a typed tenant/portfolio/security/transaction/epoch/quantity
receipt under portfolio and state write locks, the existing replay lock, and a history read lock.
Before continuing, it also qualifies the exact pre-existing cashflow semantic receipt and the
complete governed historical cashflow output, including lineage and economic/group identities.
History alone cannot admit a pending cash transaction. A distinct first-publication route is
limited to fresh ordinary CLAIMED, unversioned input: before costs, the current UOW retains
canonical tenant/key/full original fingerprint authority under the existing source and cost
locks. The current successful cost member must match that proof and the exact typed locked
position epoch/quantity receipt at the initial locked epoch zero before native CURRENT_BOOKING
cashflow processing. This shortcut cannot grant first financial publication from nonzero history
established by repair or replay; the existing persisted financial-effect fallback and authorized
repair remain available at their authoritative epochs. Zero quantity is valid; unknown epoch or
absent quantity is not. Generated members cannot inherit the root's
proof. Missing optional proof preserves the old persisted-effect guard and unrelated noncoalesced
behavior. Repair, correction, duplicates and stale epochs retain their existing fences. All source,
financial, readiness and outbox effects commit or roll back in the same UOW.

For example, an earliest DEPOSIT1000 can materialize a same-day pending DEPOSIT500 position1500
or SELL100 position900 before that pending transaction's first financial delivery. Qualified
first publication creates native +500 external deposit cashflow or +100 internal sale proceeds
exactly once at the locked epoch. SELL reduces position quantity by100, but its cash-ledger
proceeds are positive; cost reduction and analytics investment measures have distinct signs.
Existing positions are not rebuilt; duplicate delivery stages no further effects.
This admission does not certify HTTP/Kafka/live joined processing or broader concurrency.
Declared FX contract open/close no-cash
routes require a distinct pre-existing scoped stage receipt and absence of a transaction/epoch
ledger; absence alone never authorizes them, and no zero-valued cashflow is fabricated.

Full and date-bounded history replay share the existing derived financial projection and actual
portfolio cost method. Fee presence is qualified in a bounded batch against an original full hash
or independently committed scoped material receipt before derived calculation. In this separate
derived context, a stale aggregate cannot replace hash-qualified named fees, including explicit
zero; default original-source validation retains its aggregate equality and source refusals.
The financial fingerprint does not bind tenant: tenant ownership comes from scoped portfolio
admission and SQL joins, while raw/retained receipt scope is checked independently. Derived
booking identities and fee values do not rewrite or certify original source evidence. The bounded
reader preserves legacy representation when no original hash exists; that representation is not
qualified source authority, and the exact coalesced financial lookup refuses it. The bounded
replay query retains its prior anchor, date limit and deterministic order rather than loading
whole history and filtering it in memory.

The bounded fee loader reuses exact semantic scopes and correction hypotheses only within one row's batch
invocation. Defensive canonical and positive-fee snapshots invalidate preparation when inputs
change across awaits. Query-positive preparation does not replace canonical fee validation or
raw/retained receipt authority; ordinary semantic and correction identities remain distinct.
Prepared projections are immutable and returned fee dictionaries remain independent. Standalone
qualification keeps the same validation and refusal contract without a persistent or cross-row
cache. This reduces repeated client preparation without certifying database lock or load latency.

An admitted correction or repair carries one immutable root identity and complete cost-result
member group within the same unit of work. Position replay requires the active member's exact
persisted row, locked replay epoch, scope, material and financial/lineage equality before deleting
history; unrelated historical rows still require independent source qualification. Generated cash
members use the actual canonical upsert return and explicitly retained source epoch. Nonpersistent
lot-restatement context is accepted only when its complete finite Decimal values exactly match the
existing transaction-type direction and lot-restatement policy; it is not copied into future replay.

For historical derived financial reads only, an independently committed exact correction receipt
may bind the corrected material cut after the ordinary receipt's epoch/version fence is checked.
Both retained-receipt and derived-financial modes are required. Exact computed keys are read in
one additional bounded, locked batch after fee facts, with a unique fee-presence projection; no
per-row lookup, latest-receipt guess or uncommitted invocation identity qualifies. Original raw
authority, full hash and ordinary receipt remain unchanged. This scoped source contract does not
certify a supported correction writer, registered recovery endpoint or live joined safety.

For gross 50, qualified named fees 1.25 + 0.75 yield outflow 52; explicit-zero named fees yield
outflow 50 even when the persisted derived aggregate is stale 99. Absent named fees with an
authoritative original booking aggregate 99 yield outflow 149. The worked table in
`wiki/Transaction-Processing.md` distinguishes derived stale values from original booking inputs.

Canonical fee replay is service-qualified through the existing reader/publisher ports; shared
SQL loads bounded source facts without importing service policy. Original full-hash-qualified
raw evidence preserves named amounts and None versus explicit zero. Prior-claimed replay without
that raw receipt may use only an independently committed exact tenant/service/portfolio/ordinary
semantic-key processing receipt and the unchanged service material identity. At most32 component
presence hypotheses, or64 including aggregate None/zero when no positive amount contradicts it,
must yield one exact retained match. Generated booking defaults use the existing domain policy;
custom source metadata and economics remain material. No arbitrary amount reconstruction,
timestamp/latest receipt selection, source epoch substitution or raw-retention guarantee applies.
First-CLAIMED source validation disables receipt fallback, so its new claim cannot certify itself.
Source-booked v2 FX disagreement never downgrades to v1; v1 cannot prove historical source FX.
Absent/conflicting evidence or another epoch remains an authority gap requiring disposition.

Processing locks cost/security and applicable group before Portfolio then Transaction, followed
by referenced source read locks. Replay captures roots in deterministic order and rechecks scoped
source facts; bounded fee/raw/receipt families are indexed once per batch and all members qualify
before publication. Native tests must demonstrate actual supported writers, drift refusal and
rollback; read locks do not certify absent-row phantoms or global source concurrency.

Retained legacy cashflows can still lack same-epoch history. Inspect the reader's captured epoch
and selected transaction/epoch keys before classifying an orphan; historical rows superseded in
the same cut are not current failures. Use the supported canonical transaction repair path under
operator authorization and verify the resulting exact source keys, dates, signed amounts and
readiness before promotion. Do not overwrite old epochs, remove the reader refusal or assume a
clean seed qualifies deployed history. See [Transaction Processing](wiki/Transaction-Processing.md).

### Scoped price correction practice

Authoritative source ingress stages typed `AuthoritativeMarketPriceAuthorityChanged` intents
in the existing price outbox within the source-write transaction. Previous/accepted revision
evidence and each affected tenant/book/security/date bind a transport-neutral correction ID;
the payload supplies no calculation price. The price consumer strictly dispatches this family
and atomically pages all visible held current-epoch positions, job upserts and idempotency.
Workers resolve persisted authority. Never substitute legacy security-global replay or an
unscoped quote projection for this path. Scoped recovery does not qualify future/calendar,
derived propagation or latest-revision publication, and does not change QCP date coherence.

`ClientRestrictionProfile:v1` ranks effective authoritative revisions before the active-only
filter. Preserve inactive/suspended version and lineage in the inclusive view, and keep empty
current evidence INCOMPLETE. Restriction admission trims selectors and rejects any blank element;
legacy unusable scoped evidence remains retained and qualifies the profile UNAVAILABLE/INVALID
rather than broadening into a READY global rule. Intentional selector-free client/mandate controls
and the existing OR across populated selector families remain supported. The owning contract is
[client restriction authority](docs/integration/client-restriction-profile.md); this does not
extend the existing QCP restriction family's tenant-isolation claim.

`lotus-core` is the authoritative financial system of record for foundational portfolio,
account, holding, mandate, transaction, position, cash, valuation, cashflow, and historical state
used by the Lotus ecosystem.

Core owns source facts and their financial, temporal, tenant, lineage, audit, replay, and recovery
semantics. Downstream services consume those governed facts; they must not reconstruct competing
Core truth.

`PortfolioLiquidityLadder:v1` treats a missing value, unusable valuation status, or missing/blank
asset-class authority as unavailable evidence, never as economic zero. Cash-derived availability
and shortfall fields remain nullable until opening cash is known; non-cash totals remain nullable
when valuation or instrument classification is incomplete. Degradation details retain the selected
snapshot's source chronology rather than substituting the requested as-of date.
Booked and projected cashflow components retain their independent source truth, and consumers must
honour bounded degradation reasons before drawing funding conclusions.

For transaction economics, an admitted positive `transaction_fx_rate` is source-booked historical
cost authority. Cost enrichment derives reference FX only when that field is absent; generated
settlement cash uses the supplied rate or derives at settlement date, and ordinary replay preserves
the booked result. Valuation/reference FX remains a separate effective-dated authority.
The processor persists server-owned FX origin so only source-booked rates affect correction
identity. Generated settlement cash resolves its instrument currency from Core reference data and
rejects a mismatch before writing the child. The tenant/portfolio/effective-date cash-account
mapping owns the cash security and account currency; an optional source instrument is only an
assertion against that mapping. The mapped instrument must exist, be classified as `CASH`, and
match the account and trade currencies before child persistence.
The processing unit of work reads the tenant-owned portfolio, active cash-account mapping, and
mapped cash instrument under PostgreSQL row locks; supported authority updates therefore serialize
before the generated child can commit, preventing a stale mapping from being persisted.
Settlement-cash resolution is shared validation/intermediate arithmetic, not a durable output
owner; the generated-cash and cashflow boundaries each normalize and bind their own receipt. When
a correction retires a generated cash leg, Core persists a transaction-policy neutralization
receipt binding the corrected source, prior child evidence, and every zeroed financial output.
New source-booked raw events use FX-sensitive v2 identity. Historical v1 compatibility is admitted
only against matching locked processed-event and transaction evidence. A non-null FX with null
origin can represent a late old worker, but remains unknown: exact numeric FX and v1 economics may
replay without origin inference or promotion; every mismatch conflicts.
Transaction processing likewise uses FX-sensitive v2 identity for source-booked FX and accepts an
already-existing v1 processing fence only by exact, read-only physical-fence qualification.
Governed transaction-type cash-entry defaults are canonical for processing identity, while a
server-resolved cash security remains derived context and never rewrites source identity.

## Business And Domain Responsibility

Generated settlement cash receipts use algorithm `generated-settlement-cash` version 2 to
bind the exact transaction-ledger FX-rate representation before persistence. The local
builder validates finite/exact `TRANSACTION_PERSISTENCE_PRECISION_V1` bounds first, then
represents the admitted rate at that policy's scale under local working precision. It does
not round source rates, rewrite original input hashes, change FX provenance, or normalize
global lineage. Version 1 receipt bytes and decoders remain unchanged; a historical receipt
qualifies only when it binds its actual persisted output. Unscaled-rate version 1 receipts
that fail binding remain unqualified. Preserve their receipt/raw evidence before separately
authorized source-based repair; this change provides no retrospective re-hash, automatic
backfill, migration or new repair command. See #1228 and the FX Slice 6 generated-cash
representation note; returned-value unit proof and actual PostgreSQL reload proof are distinct.

Fresh applicable canonical FX `UPSTREAM_PROVIDED` ingestion requires both local/base FX P&L;
explicit zero is source evidence and totals cannot replace missing FX. Shared domain admission
governs HTTP and raw persistence; `FX_CONTRACT_OPEN`/`NONE` are exempt. HTTP resubmission is
strict-forward. Broker duplicates precede admission inside the existing UOW; fresh refusal must
leave no ledger/outbox/fence. Locked immutable v3 durable identity can qualify exact replay after
fence expiry. Raw upstream v3 hashes all six original P&L fields; ambiguous P&L-excluding v1/v2
identity cannot qualify upstream replay or promote stored zero. No historical row, calculation,
receipt or correction command changes in admission. Native candidate-specific PG proof is routed through
`transaction-fx-contract` and `critical-db-coverage`; unit mocks are not durable evidence.

The QCP `PerformanceComponentEconomics:v1` reader separately qualifies historical applicable FX
using retained immutable raw outbox evidence, persisted portfolio tenant ownership, source identity,
the strict shared lineage decoder and complete existing FX receipt output binding. Stored zero and
normalized version-1 receipts alone never prove original presence. Missing FX bases and dependent
totals remain nullable, missing contributors prevent complete grouped totals, and source-safe reasons
qualify supportability as DEGRADED/PARTIAL. Qualified explicit zero is observed evidence; explicit
NONE/non-realizing and non-FX semantics remain supported. Reads do not backfill ledger, outbox or
fences. Owning reader proof runs in `query-authority-db-contract` and `critical-db-coverage`; actual
downstream consumer and exact-main release qualification remain distinct acceptance boundaries.

Evidence-only source confirmation is a separate signed command, not financial correction.
The source-owned append-only revision binds tenant, retained raw/output/receipt, initial head,
purpose-bound grant, CAS and original source presence. Persistence commits the revision and
notice atomically; retries and status independently verify committed authority. The baseline
v2 producer preserves all six original P&L presence/value pairs before unchanged normalization.
QCP and operational ledger readers share qualified current/original/explicit-revision evidence
and bind the material snapshot/source cut; missing authority stays unavailable. Original raw,
receipts, signed companions, capital/total values and cash/cost/replay effects remain immutable.
Source-cut booked-output material preserves every field/null and validates exact transaction
persistence precision before context-independent fixed-scale Decimal encoding. Equivalent scale
and signed zero bind identically; quantum changes remain material. This is not global lineage/raw/
receipt/revision/CAS normalization. NEW confirmation values encode unsigned zero before their
receipt/material/revision hash; persisted revision history is never re-encoded. The calculated-output
guard structurally proves exact material encoding and bounded hash/lineage consumers rather than
allowlisting a lineage gap. Earlier unmerged cut encodings require continuation restart.
The implementation contract is `docs/rfc-transaction-specs/transactions/FX/FX-SLICE-6-PNL-SEMANTICS.md`;
native consumer/database, exact protected promotion/release, deployed enrollment, live Kafka and
downstream analytics qualification are distinct proof boundaries. Broader economic corrections
remain separately owned by #452.

The #452 R2 persisted-return candidate carries a detached FX pre-write witness and actual
first-publication/epoch context through cost processing. Reuse the canonical loader's existing
raw facts and locks; fallback reads lock only the owning transaction row. `NONE` raw absence
does not certify source evidence; `UPSTREAM_PROVIDED` requires original raw material and, for
processed rows, a qualified retained receipt. Only witnessed omitted source-system or creation
timestamp retention is allowed on the first return. Fresh witnessless rows with absent chronology
admit the same PostgreSQL transaction timestamp through the owning FX port before projection,
without a new session, commit or lock. Existing witnesses and supplied timestamps need no extra
query. Creation chronology remains bound in the output receipt; the rebound return is exact and
preserves original six P&L values.
When qualifying original JSON raw, reuse the supported event parser for typed date identity.
Keep raw JSON/hash/event ID unchanged; verify the internal projection preserves aware instants,
absent/null presence and all non-time facts. Never substitute enriched ledger defaults for raw
source or rewrite the shared identity policy to make a retention witness pass.
For contract-open returns, retain an omitted original open-transaction link in the detached
witness while qualifying only the existing derived self-link. Position comparison may project
that self-link and original omitted mode to the existing `NONE` default only with a genuine
output-bound FX baseline receipt; explicit modes/links and other material remain exact. Keep
original root/admission, raw facts and global semantic identities/historical hashes unchanged.
Scoped actual UOW rollback/retry evidence is separate from account-admission negatives,
competing-writer lock behavior and concurrency/scale, which remain unproven by this slice.
Do not weaken `FirstPublicationSourceAuthority.matches`, add broad portfolio serialization or
claim native rollback/concurrency/main acceptance from local units. Native PG and promotion
remain separately admitted boundaries in the FX Slice 6 contract.

Source-confirmation applications consume framework-neutral operation ports and detached immutable
source facts, not ORM rows or the legacy ingestion job service. The SQL adapter projects every
transaction column except `id`, `updated_at`, `payload_fingerprint` and `calculation_lineage`;
fingerprint and original receipt remain separate complete authority. Every revision column is
required by the explicit fact schema; schema drift refuses rather than silently dropping fields.
Nested source/receipt material is frozen, and projections return fresh JSON-compatible containers.
Framework validation stays in the native adapter and returns typed refusal to the application at
the original qualification boundary. The adapter borrows the consumer's UOW; it preserves the
operation-before-source lock order and stages revision plus notification without committing it.

### Retained-verification delivery practice

Typed retained-source proof additionally requires an exact original-six P&L presence/value
projection for a registered algorithm version greater than one. Its finite immutable basis,
receipt input/output binding, shadowing, mutation and helper reachability are structurally
qualified; explicit zero is not absence. The projection helper inspects AST only. Independent
fixed owner fixtures exercise valid and refused grammar without reading live producer source.
This static capability does not activate a production v2 boundary, qualify PostgreSQL or
confirm downstream consumers; those remain separately owned integration requirements.

Presence-owner module bindings use a closed inert-declaration grammar: only the supported
standard-library imports, literal module bindings/defaults, approved type annotations and
undecorated functions are admitted. Evaluated calls in definition headers are refused even
on unrelated functions. Unrelated function bodies are not a general purity proof; selected
projector and builder bodies still require their separate exact structural templates.
Every function declaration in a registered retained-owner module also requires inert defaults,
resolved supported type annotations and no decorators, including unrelated functions and class
methods. Typed immutable evidence and literal type aliases retain their separate structural
qualification. This header check is not a general import or function-body purity proof.

Calculated-output declaration, usage and caller-graph scans share the same authored-source
selection below `src/`. Directory components named `build` are generated packaging inputs,
as declared by `.gitignore`, and are excluded without deleting their files. Newly authored
untracked Python files remain visible; files named `build.py` and directories such as `buildings`
are ordinary source. An empty authored-source inventory fails closed. This selection does not
change financial lineage boundaries, terminal classifications or required binding.

`make calculated-output-policy-guard` recognizes retained receipt verification separately from
producer receipt creation. A registered straight-line boundary must import the shared strict
decoder and output-binding predicate, reject missing/wrong algorithm, precision and complete
numeric-policy identity, and reject a false binding against the same declared output before
covered amount arithmetic. Covered helpers remain subject to exact caller reachability and
escape checks. Unsupported branch/exception/decorator shapes, discarded or inverted predicates,
input reassignment and opaque mutation fail closed; no arbitrary terminal or new lineage gap
is permitted. Covered local helpers use the same named output parameter or a single output
parameter. This is static source proof, not PostgreSQL, consumer or release certification.
Canonical projection is a checked premise: only same-key input field normalization or an
alpha-renamed complete mapping copy that omits only None and applies governed Decimal
normalization/quantization is recognized. Constant/remapped/opaque projection shapes and
alias-bearing containers, closures or computed assignments fail closed. Passing the input
argument or reading it and then returning an unrelated value is not projection authority.
Covered amount helpers must be read-only and return normalized immutable Decimal/None values;
registration or annotations alone cannot prove that their result contains no mutable input alias.

Core owns:

1. tenant-owned portfolio, account, holding, instrument, mandate, and transaction records;
2. source ingestion, validation, persistence, and correction lineage;
3. supported transaction and corporate-action economic effects;
4. dated positions, cash, valuation, cashflow, and time-series foundations;
5. source-data products and operational, analytics-input, lineage, policy, support, snapshot,
   simulation, and export contracts;
6. reconciliation, idempotency, fencing, replay, reprocessing, and recovery evidence.

Core does not own performance or risk conclusions, advisory recommendations, mandate decisions,
client report composition, or the unified front-office experience. Those remain with their
respective Lotus services.

## Consumer Native-Operation Practice

Operator subclasses such as `DLQReplayConsumer` must delegate polling, exact offset acknowledgement,
drain and close to `BaseConsumer.run()`. A deadline stops admission; already submitted native work
is joined before close and may exceed that deadline. Replay publish and confirmed flush share the
owned native lane. Failed replay stops admission without offset acknowledgement; malformed DLQ
records are explicitly discarded without republishing before continuing to valid records. Run the
tool's direct static checks and owning tests: repository-default `src` gates omit `tools/`.

Shared Kafka consumer contract changes must inspect every concrete caller fixture and execute
the full affected caller test set alongside the common consumer/native/supervisor controls.
Positive synchronous-commit fixtures must return real acknowledgement-shaped values for the
message's topic, partition and next offset, with no partition error; a commit-call assertion alone
does not establish successful acknowledgement. Preserve negative acknowledgement and drain/order
assertions when updating fixtures.

`BaseConsumer` uses one owned FIFO worker for native construction/subscription, poll, pause/resume,
synchronous offset acknowledgement, cached watermark reads, DLQ confirmation and close. Keep
async financial UOWs and metrics on the event loop. Await exact topic/partition/next-offset success
before releasing partition order; a successful native call alone is not partition acknowledgement.
Rebalance callbacks only invalidate generation state and must not wait reentrantly on the worker.
Cancellation joins the submitted operation before resource close; runtime supervision also awaits
`wait_closed()`. Native work may exceed supervision grace because asyncio cannot preempt it.
Concurrent active polls use native timeout zero. An empty result waits for processing completion
on the event loop, bounded by the smaller of the configured timeout and 100ms, leaving the FIFO
worker free for acknowledgement and cached watermark operations. Keep configured idle/serial
polling and poll callback service between waits. Event-barrier scheduling tests do not replace
exact-source Kafka, financial PG or full-load qualification.

The recording regression reproduces the prior loop stall and tests responsive unrelated UOW work,
ordering, ownership, acknowledgement errors and actual supervisor drain. It does not certify
broker/PG semantics, deployment teardown bounds, full-load causation or accepted main. #795,
#730 and the #483 rebuild alternative remain bounded as described in the
[partition runbook](docs/operations/kafka-partition-migration-runbook.md#native-consumer-operations-and-shutdown).
Financial locks, epochs, SQL atomicity, topology, pool sizes and SLOs retain their existing policy.

## Current-State Summary

- `query_service` is the operational read plane.
- `query_control_plane_service` owns governed analytics-input, source-product, lineage, policy,
  support, snapshot, simulation, and export contracts.
- `ingestion_service` owns HTTP/source adapters and delegates write lifecycle orchestration to
  application commands rather than routers.
- `portfolio_transaction_processing_service` is the combined app-local and CI runtime for atomic
  cost, cashflow, position, and transaction-readiness effects. Valuation remains independently
  scalable.
- `portfolio_derived_state_service` materializes position and portfolio time series and owns
  aggregation scheduling; `financial_reconciliation_service` owns reconciliation lifecycle and
  durable control evidence.
- `event_replay_service` owns DLQ, replay, ingestion-health, audit, and remediation operations.
- Tenant ownership is enforced for validated ingress and durable root portfolios. Enforcement
  across all fences, ledger records, derived state, queries, replay, and operations is incomplete
  under #798; the invariant below governs new work but does not certify shared multi-tenant use.
- Source-effective valuation readiness is tied to current source facts, valuation epoch, and
  reconciliation state. Benign bookkeeping cannot invalidate unchanged facts; reprocessing,
  changed facts, or epoch mismatch cannot reuse stale evidence.
- Historical position reads share one dated snapshot/history-and-instrument timestamp projection
  for reconciliation scopes and public evidence identity; shared PositionState completion timestamps
  are excluded, while epoch/status qualification remains material. Exact control failures have
  reconciliation-scoped degradation reasons. See the [Holdings As Of methodology](docs/methodologies/source-data-products/holdings-as-of.md);
  cash-balance timestamp semantics are unchanged.
- Source-data product declarations, feature status, route families, RFC status, and runtime
  validation are machine-checked. A declaration or local test is not production certification.

Current implementation status is maintained in the
[supported-feature contract](contracts/supported-features/lotus-core-supported-features.v1.json),
[Supported Features](wiki/Supported-Features.md),
[API route catalogue](docs/standards/api-route-catalog.v1.json), and
[RFC status ledger](docs/standards/rfc-status-ledger.v1.json).

## Financial System-Of-Record Invariants

Every Core change must preserve the following:

1. **Exact economics.** Money, quantity, rates, fees, taxes, FX, and cost use governed exact
   numeric semantics and explicit rounding policy.
   The operational BUY lots route preserves `PositionLotState` quantity Decimals through
   `PositionLotRecord` and emits `original_quantity`/`open_quantity` as exact JSON decimal strings,
   as it already does for costs. Consumers parse the strings directly without binary-float
   conversion; Gateway's immediate lot consumer uses Decimal. This wire correction leaves the
   separate dated `PortfolioTaxLotWindow` contract unchanged.
2. **Temporal truth.** Trade, settlement, booking, effective, observation, valuation, correction,
   and ingestion time are distinct. As-of queries cannot silently switch semantics.
   `PositionTimeseriesInput` aligns internal investment position flows to the linked transaction's
   UTC trade date because position ownership is trade-date recognized; it does not change the
   settlement-dated cash ledger or external-flow chronology. Select the latest cashflow epoch
   before applying analytics window and security filters so a restatement cannot revive old facts.
   Resolve that trade date from same-epoch position history, not the mutable current transaction;
   missing epoch evidence fails closed rather than inventing a date for a prior snapshot.
3. **Tenant authority.** One validated source-owned tenant identity flows through request,
   application, persistence, jobs, events, replay, and reads; missing authority fails closed.
4. **Deterministic replay.** The same authoritative inputs, versions, and ordering reproduce the
   same outcome. Corrections preserve earliest affected scope and current lineage.
5. **Idempotency and fencing.** Duplicate delivery, stale leases, old epochs, and superseded jobs
   cannot overwrite newer authoritative state.
6. **Lineage and audit.** Derived values remain attributable to source batches, prices, FX,
   policies, versions, correlations, actors, and decision evidence.
7. **Reconciliation and readiness.** Missing, stale, malformed, mismatched, or unresolved evidence
   returns an explicit unavailable/blocked state; Core does not invent a plausible value.
8. **Operational recovery.** Failure, restart, timeout, poison work, and partial progress reach a
   controlled recoverable or quarantined state without losing financial truth.

## Architecture And Module Map

Incremental cost persistence admits an absent acquisition-lot dependency from an eligible historical
lot-opening prefix before writing disposal allocations, under the incoming stream's resolved tenant
and locked durable source/portfolio authority. This absent-only boundary preserves an existing
residual lot and does not replay the acquisition's child effects; later refusal rolls admission back
in the same unit of work. See the [cost developer guide](docs/features/cost_calculator/05_Developer_Guide.md#3-acquisition-lot-dependency-admission)
for source identity qualification and distinct FK/receipt-version collision classification.

| Area | Ownership |
| --- | --- |
| `src/services/ingestion_service/` | Source-data and adapter write ingress; command-owned ingestion lifecycle. |
| `src/services/portfolio_transaction_processing_service/` | Atomic cost, cashflow, position, replay, rollback, and readiness effects. |
| `src/services/calculators/` | Independently deployable position valuation. |
| `src/services/valuation_orchestrator_service/` | Valuation scheduling, job lifecycle, reprocessing state, and dispatch. |
| `src/services/portfolio_derived_state_service/` | Position/portfolio time-series materialization and aggregation scheduling. |
| `src/services/financial_reconciliation_service/` | Reconciliation run/finding policy, control evidence, and completion events. |
| `src/services/query_service/` | Operational portfolio, position, transaction, cash, market, and reporting reads. |
| `src/services/query_control_plane_service/` | Analytics-input, snapshot, simulation, source-product, lineage, policy, support, and export contracts. |
| `src/services/event_replay_service/` | Replay, DLQ, ingestion-health, audit, and remediation control plane. |
| `src/libs/portfolio-common/` | Shared financial domain and contract-support primitives; not a dumping ground for service orchestration. |
| `contracts/` | Machine-readable feature, eventing, source-product, security, CI, and trust contracts. |
| `scripts/` | Purpose-owned quality, validation, operations, release, development, and generation automation. |
| `docs/` | Detailed architecture, methodology, standards, features, testing, and operations truth. |
| `wiki/` | Authored source for concise GitHub wiki navigation and operator guidance. |

Use the [current-state architecture map](docs/architecture/current-state-architecture-map.md),
[target architecture](docs/architecture/lotus-core-target-architecture.md),
[architecture index](docs/architecture/README.md), and
[service boundary map](docs/architecture/microservice-boundaries-and-trigger-matrix.md) for deeper
structure and event-flow detail.

## Runtime And Integration Boundaries

1. Core-owned writes enter through governed ingestion or service application boundaries and retain
   source identity, tenant, correlation, and idempotency evidence.
2. PostgreSQL is authoritative persistence. Kafka/outbox paths distribute facts and commands but
   do not replace durable state ownership.
3. `query_service` and `query_control_plane_service` have distinct route families; do not move a
   route or duplicate logic without updating the RFC-0082 registry and consumer evidence.
4. Downstream analytics receive source-owned facts and readiness, not permission to reinterpret
   missing evidence or broaden tenant scope.
5. Local Compose is isolated Core development. Shared infrastructure belongs to Platform; the
   populated integrated front-office runtime belongs to Workbench.
   Use `make docker-up` for a source-attributed local build. It derives checkout provenance once
   and supplies it to every Compose-built service; direct `docker compose up --build` cannot
   authoritatively derive Git or dirty-tree state.
6. Promoted runtime claims require exact image, deployment, dependency, migration, observability,
   IAM, and operational evidence. Local green tests are not that certification.

## Task Routes

| Task | Read next |
| --- | --- |
| Architecture or ownership | [Architecture index](docs/architecture/README.md) and [current-state map](docs/architecture/current-state-architecture-map.md) |
| API or downstream integration | [RFC-0082 inventory](docs/architecture/RFC-0082-contract-family-inventory.md), [API Surface](wiki/API-Surface.md), route catalogue and registry |
| Financial or transaction behavior | [Transaction capability catalogue](contracts/transaction-processing/transaction-capability-catalog.v1.json), relevant transaction RFC, and domain tests |
| Time/as-of semantics | [Temporal vocabulary](docs/standards/temporal-vocabulary.md) and the owning schema/methodology |
| Source-data products | [Source-product catalogue](docs/architecture/RFC-0083-source-data-product-catalog.md), `contracts/domain-data-products/`, and relevant methodology |
| Reconciliation or data quality | [Reconciliation target model](docs/architecture/RFC-0083-reconciliation-data-quality-target-model.md) and recovery runbooks |
| Tenant, security, or audit | [Security/tenancy target model](docs/architecture/RFC-0083-security-tenancy-lifecycle-target-model.md) and [Security and Governance](wiki/Security-and-Governance.md) |
| Migration or PostgreSQL behavior | [Migration contract](docs/standards/migration-contract.md), migration files, and real PostgreSQL proof guidance |
| Replay, jobs, or recovery | [Recovery index](docs/operations/recovery/README.md), [transaction replay standard](docs/standards/transaction-replay-boundary-standard.md), and owning application state machine |
| CI, tests, or quality gates | [Validation and CI](wiki/Validation-and-CI.md), relevant contract under `docs/standards/`, and the repo-native Make target |
| Operations and incidents | [Operations runbook](docs/operations/runbook.md), [observability](docs/operations/observability.md), and incident playbooks |
| Documentation or wiki | [Docs index](docs/README.md), front-door contract, and Platform documentation-layering guidance |

## Repo-Native Commands

Run from the `lotus-core` repository root:

```bash
make install
make ci-local
make ci
make ci-main
make front-door-sync-guard
make quality-wiki-docs-gate
make docs-evidence-pack
make lotus-core-validate
```

Use focused Make targets listed in the [Development Workflow](wiki/Development-Workflow.md) for
fast fix-forward proof. Do not replace a governed target with an ad hoc command that changes the
interpreter, dependency, database, Compose, coverage, or failure-propagation boundary.

## Validation And CI Expectations

Core uses Remote Feature Lane, Pull Request Merge Gate, and Main Releasability Gate. The applicable
lane must pass against the exact implementation SHA.

Python 3.11 is the shipped runtime and validation authority recorded in `.python-version`.
Workflow, Dockerfile, package-floor, Ruff, mypy, and Windows lock-replay parity is enforced by the
workflow-governance suite; do not change one surface independently.

Rebase merges dispatch Main Releasability independently for every landed revision. The dispatcher
proves the exact base-to-merge range and PR patch identity, while `make main-gate-coverage-audit`
fails closed on any post-enforcement revision without a verdict-bearing run. Release-evidence runs
are non-cancellable; duplicate, cancelled, pending and historical failing attempts remain visible.

Tests must prove the economic invariant, edge/failure behavior, replay or idempotency semantics,
and contract meaning—not merely execute lines. Use real PostgreSQL when correctness depends on its
SQL, types, constraints, locks, transactions, or persistence behavior. Concurrency proof must force
the claimed ordering and assert the database observation rather than only synchronizing callers.

Completion requires:

- focused proof plus the applicable repo-native lane;
- no weakened assertions, exclusions, compatibility paths, or hidden command failures;
- resolved blocking review findings after the latest implementation commit;
- updated contract, docs, context, feature, RFC, runbook, and wiki truth where affected;
- wiki publication and strict parity after merge when wiki source changes;
- exact-main validation and clean branch/worktree state;
- GitHub issues reconciled to what remains.

### Delivery practice

Maintain one active implementation slice and freeze its PR revision while required CI runs. Prepare
the next three prioritized invariants through read-only analysis, expected figures, and reproducer
design; do not mutate the candidate to fill wait time or share a mutable financial test stack.

Before pushing, run previously failing inexpensive checks, the complete affected-caller invariant
matrix, and pinned `make quality-ruff-gate quality-ruff-format-gate` after the final edit. Record the
exact revision, native exits, CI run IDs, independent acceptance, and separate implementation,
local-proof, queue/run, and review-rework time. Earlier evidence is reusable only when its source,
dependencies, fixtures, contract, and environment are unchanged.

Workflow optimizations must preserve required checks, exact-source identity, warning and coverage
policies, complete main certification, and final wiki parity. A merged-and-validated slice—not a
passing narrow test or issue count—is the unit of delivery.

Main Releasability starts Integration Full alongside the test/coverage matrix after the existing
lint/typecheck/contracts/security prerequisite. That prerequisite retains Windows lock replay and
exact-revision admission. Integration Full consumes no coverage artifact; its complete selector,
isolated runtime and diagnostics remain unchanged. Combined coverage still gates Docker build and
its downstream runtime jobs. A passing integration job alone cannot establish release success:
coverage and every other applicable release job must also pass. Measure hosted makespan before
claiming a scheduling improvement; earlier admission is not a smaller certification scope.

DPM mandate population readers resolve one effective authoritative revision per portfolio and
mandate within the admitted tenant before applying model, booking-center, or authority-status
membership filters. Reuse the authority predicates and precedence in
`effective_mandate_sources.py` for per-portfolio binding and population selection. A same-date
observed correction replaces the earlier revision for that effective interval; a future-effective
change remains invisible before its start date. Keep real PostgreSQL and registered-route proof in
the `query-authority-db-contract` suite when changing this selection boundary.

## Standards And RFCs That Govern This Repository

Primary authorities:

1. [RFC-0082 contract-family inventory](docs/architecture/RFC-0082-contract-family-inventory.md)
2. [RFC-0083 target architecture](docs/architecture/lotus-core-target-architecture.md)
3. [Temporal vocabulary](docs/standards/temporal-vocabulary.md)
4. [Application-layer contract](docs/standards/application-layer-contract.md)
5. [Repository transaction boundary](docs/standards/repository-transaction-boundary-standard.md)
6. [Runtime boundary decisions](docs/standards/runtime-boundary-decision-standard.md)
7. [Migration contract](docs/standards/migration-contract.md)
8. [Risk-based test matrix](docs/standards/risk-based-test-coverage-matrix.v1.json)
9. [Critical-path coverage contract](docs/standards/critical-path-coverage.v1.json)
10. [Front-door synchronization contract](docs/standards/front-door-sync.v1.json)

Use the [RFC Index](wiki/RFC-Index.md) for current status. RFC prose does not override current code,
schema, machine-readable contracts, or executable evidence.

## Known Constraints And Implementation Notes

- The framework-neutral domain kernel registers exact day-count convention versions.
  `30/360.US@1` retains historical Lotus/SIFMA calendar-basis replay;
  `30/360.US@2` is the explicit U.S. EOM policy and adjusts the end day only when both dates are
  February month-end. Never infer a latest version or rewrite v1 evidence. The version participates
  in accrued-income input, calculation, and output lineage. No runtime, API, or database boundary
  selects or persists `30/360.US@2` in this slice; issue #788 owns that integration.
- QCP snapshot freshness must reuse the already-computed governed collective reconciliation
  scope. Per-security epochs record last mutation and may differ in a valid current portfolio;
  do not introduce a second epoch resolver or default target. Empty/unscoped source evidence
  remains unknown, and completed exact controls plus coherent current valuation evidence are
  still required. Production-route PostgreSQL controls are selected by lifecycle and bounded
  coverage suites; see [collective freshness review](docs/architecture/codebase-reviews/CR-1726-CORE-SNAPSHOT-COLLECTIVE-FRESHNESS.md).
- Position-timeseries materialization promotes latest non-zero `PositionHistory` business dates
  at every explicitly changed or carry-forward-restaged as-of boundary to the collective source
  epoch inside its portfolio
  aggregation advisory fence and transaction, including unavailable-valuations. A later close
  must not hide the business date selected before that close. The aggregation-day job carries
  a durable full-sweep epoch sentinel: first work at that day/epoch selects the portfolio once;
  later same-epoch snapshots
  use the Python-strip-equivalent indexed latest-history lookup for their own security, so a late
  fact or legacy boundary-whitespace identifier is still covered
  without quadratic portfolio scans. Its tenant-scoped per-security observation stores the exact
  selected economic fact, excluding timestamps; a changed late fact can rearm an equal-epoch old
  control, while replay of the same fact cannot. Migration `c171b2c3d532` starts existing jobs
  at `-1` for one safe post-upgrade sweep and adds its large-table checks as `NOT VALID`;
  `c172b2c3d533` validates existing rows after the column-add lock is released. The
  position-history lookup index is built and dropped concurrently with retry-safe shape checks.
  An unseen selected fact is changed evidence even when its pre-migration control is already
  COMPLETE at the same epoch; the fact index lets later
  as-of sweeps skip identical history. Strictly higher-epoch writes remain the default;
  equal-epoch historical restaging requires changed selected-fact evidence. The aggregation
  lease, source revision, outbox, and reconciliation consumer own completion. Do not
  rewrite old facts, infer business dates from valuation/serving timestamps, or synthesize a
  control in the query plane; see #1134.
  A selected-history observation records exact source selection. A separate tenant-scoped
  per-fact valuation state records READY/UNAVAILABLE transitions; the first later success,
  failure, or recovery for that same fact rearms its historical control even when the collective
  epoch matches. Attribute an outcome only to a selected fact at or before the delivered snapshot
  epoch and no later than the delivered valuation business date; one replay epoch can hold
  several dated facts, so an earlier snapshot cannot certify a later fact. Store the delivered
  valuation epoch/date with the outcome so an older same-security event cannot overwrite newer
  READY/UNAVAILABLE state or reopen its historical control. Repeated daily outcomes and unchanged replay remain
  no-ops. A command restaging many dependent days prepares one transaction-local selected-history
  batch from the latest per-security baseline plus effective-date interval changes; each day then
  reads that indexed batch, not the entire portfolio history. Sequence changes before joining
  affected dates, so intermediate restatements do not multiply into every later day's ranking input.
  Before a full-sweep observation upsert, include the prior selected non-zero date when the
  selected fact closes or changes; otherwise the replaced observation can erase the only durable
  pointer needed to rearm an equal-epoch historical control.
  Preserve the source scan bound, zero-quantity closures, exact per-day observations and atomic
  job/marker writes under the portfolio lock.

- `PortfolioTimeseriesInput:v1` and `PositionTimeseriesInput:v1` declare the governed `GLOBAL`
  business calendar and therefore select served rows through `business_dates` at the PostgreSQL
  boundary. Retain raw non-business valuation history, but do not mix it into these source-product
  responses while the calendar exists. The pre-existing calendar-day recovery fallback applies
  only when the governed calendar is entirely empty; a partial calendar must not broaden scope.
  Event-driven valuation scheduling does not infer completeness from calendar bounds: an empty
  calendar retains the compatibility fallback, position readiness remains durable, historical
  off-calendar price and FX facts retain replay, and future facts wait for later readiness without
  terminating a consumer. A current-date price queues every visible non-zero current epoch whose
  same-day snapshot is absent, not `VALUED_CURRENT`, price/currency-mismatched, or older than the
  source; position-history or snapshot write time alone is not valuation-source authority. Analytics
  continuation scopes include the exact window calendar digest
  and global activation state; calendar drift rejects the next page and requires a restart instead
  of mixing snapshots.
  Calendar codes are trimmed and uppercased at both HTTP ingestion and persisted-event validation,
  so partition identity, stored rows, and `GLOBAL` membership predicates cannot diverge by case.

- Large cashflow evidence seeds must use physical multi-row SQL statements, not ORM
  `executemany` mappings that issue one statement per row. Source-cut maintenance is atomic and
  statement-scoped; preserve its durable locks rather than disabling maintenance to accelerate
  fixtures. PostgreSQL work-count controls cover single and cross-batch inserts, including the
  bank-day seed's 1,000-row physical statements inside unchanged 5,000-row commit batches.
  Source-cut work proof executes the installed refresh statement with `EXPLAIN ANALYZE`, not a
  copied query or trigger-metadata proxy. Rebuild the owned migration image when migrations change
  (`LOTUS_TESTS_DOCKER_BUILD=true` for local test execution); a cached image is not current-head
  migration proof. See the [migration contract](docs/standards/migration-contract.md).
- Historical migration tests that directly invoke c168 or c118 against a current-head
  PostgreSQL schema must account for c171's selected-history foreign keys before dropping
  c168's `uq_portfolios_tenant_portfolio_id`. A normal Alembic rollback removes newer revisions
  first; direct tests instead suspend only the two verified newer dependencies and restore/assert
  both after re-upgrade. Do not use `DROP ... CASCADE`, weaken the tenant foreign keys, or treat
  `migration-smoke` heads/history checks as executable rollback proof.
- A changed critical migration must execute under `critical-db-coverage`, not only the separate
  lifecycle matrix: the combined changed-code gate measures that lane's coverage data. Keep a
  bounded real-PostgreSQL migration selector in the manifest and prove its refusal branches;
  do not lower the 90% line / 85% branch changed-code floors to accommodate unmeasured tests.
- The native full-integration target retains per-test progress, diagnostic thread stacks after
  120 seconds, and a completed JUnit results artifact. Missing results after cancellation are not
  passing release evidence; see [Validation and CI](wiki/Validation-and-CI.md#full-integration-diagnostics).
- Shared source-product metadata changes must retain registered-route OpenAPI regression proof
  in the premerge operations contract suite. Source materialization is not transport-serving
  time, and a resolved collective snapshot epoch alone is not current reconciliation/valuation
  readiness. Test exact contract descriptions and representative wrong served-schema mutations;
  do not restore stale documentation or weaken adjacent authority/schema checks to pass tests.
- Test runtime classification uses the pytest nodeid's test-file portion, not parameter IDs
  containing example integration/E2E paths. Preserve actual file-path and explicit database-marker
  admission; verify manifest membership and omission guards execute with the ordinary unit selector.
- E2E checks for retired Core routes must call the real query HTTP surface without seeding
  unrelated portfolios, transactions, or valuation work. A `202` portfolio ingest is only queue
  acknowledgement; active transaction pipelines must wait for supported tenant-scoped portfolio
  materialization before posting transactions. Preserve fail-closed ownership rejection rather
  than masking the race with sleeps or admission bypasses.
- Source-provenance fixtures must prove foreign packages are reachable without the guard before
  asserting rejection; pinned venvs can disable automatic user-site discovery. Refresh-count
  wrappers must replan PostgreSQL expressions after function renaming, including warmed backends.

- Some external treasury and OMS source products intentionally remain unavailable until bank-owned
  integration evidence is certified; do not fabricate substitutes.
- Production security and audit defaults do not replace platform ingress, IAM, or deployment proof.
- Tenant S1, transaction event/idempotency fences, query-service portfolio/reporting reads, QCP
  transaction-economics and CoreSnapshot portfolio selection, and portfolio-aggregation job
  ownership are tenant-bound. CoreSnapshot transport must match header/body authority, its
  application port must carry typed `TenantId`, and PostgreSQL must select the portfolio by both
  tenant and portfolio before reading any snapshot, simulation, valuation, or reconciliation fact.
  #798 S2-S6 remain open: do not claim estate-wide isolation until outbox ownership, remaining
  stateful fences, ledger and derived records, other
  portfolio-owned query paths, replay, and operations are tenant-bound and exact-main proven.
  Global reference and market-data products remain explicitly global.
- Event Replay consumer-DLQ and replay-audit reads carry the admitted tenant through list,
  direct-id, job, event-id, and fingerprint selectors and apply tenant authority before limits.
  Their durable identities are tenant-scoped. Consumer-DLQ database evidence requires an owning
  ingestion job; unattributable messages remain on the broker DLQ and database indexing is refused
  with degraded telemetry rather than a fabricated tenant. Migration `c176b2c3d537` backfills only
  from the durable job/DLQ ownership chain, aborts on orphaned or conflicting history, and refuses
  downgrade when tenant-scoped identifiers collide. This delivers only #798 Slice 5, not the
  remaining tenant-isolation families or estate-wide certification.
- Financial reconciliation run/finding persistence, supported command/read routes, aggregation
  request/completion events, request-consumer fences, QCP support reads, and Bundle A corporate
  action evidence carry typed admitted tenant authority. Filter tenant before pagination or
  aggregation, return non-disclosing not-found responses, and never expose historical `ESTATE`
  reconciliation rows through tenant APIs. This does not close the remaining #798 S2-S6 families.
  Migration `c174b2c3d535` requires a coordinated drain of reconciliation writers and tenant-bearing
  event producers/consumers, zero pending legacy reconciliation events, and simultaneous deployment.
  Its five-second lock timeout is fail-closed; downgrade refuses tenant-wide runs and dedupe keys
  that cannot return to the former global constraint.
- Raw persistence source transactions retain a versioned economic-payload fingerprint on the
  durable ledger. Identical `(tenant_id, transaction_id)` replay is a no-op, transport-metadata-only
  changes remain stable, and materially changed economics fail closed at the transaction write
  boundary even after transient processed-event retention expires. This is replay protection, not
  correction authority; correction semantics remain governed separately. A same-tenant source
  replay that moves the transaction to another admitted portfolio is a material payload change and
  remains `TRANSACTION_SEMANTIC_CONFLICT`; foreign-tenant and generated-child ownership collisions
  retain their separate identity-collision classification. Fingerprinting projects transaction,
  portfolio, and generated-origin ownership identifiers through the same canonical form persisted
  to the ledger, so supported surrounding-whitespace normalization remains an identical replay;
  other material values remain exact. Historical ordinary
  source rows derive this identity only from immutable `RawTransactionPersisted` outbox evidence;
  mutable enrichment columns and derived fee rows are not reconstruction authority. Canonical
  processor-generated children use generated-row authority and refresh their fingerprint from the
  post-upsert durable row, so omitted nullable inputs retained by PostgreSQL cannot diverge from
  the stored identity. After the ownership-fenced upsert is admitted, identity is derived from a
  raw durable-column snapshot in the same transaction; neither ORM `RETURNING` state nor a
  session-cached predecessor row is post-write evidence.
  Migration `c173b2c3d534` therefore requires a quiesced
  compatibility-set cutover: stop, drain, and deploy both `persistence-service` and
  `portfolio-transaction-processing` before either consumer resumes; predecessor processors cannot
  write or refresh the new generated-child fingerprint safely. The migration stages relevant
  immutable outbox evidence once in an indexed temporary relation before bounded ledger batches,
  avoiding repeated full outbox scans while those writer fences are held.
- App-local Compose and CI use checkout-specific ownership. Never disturb the shared canonical
  runtime while validating a branch.
- Generated catalogues and evidence must be regenerated by their owning scripts; do not hand-edit
  derived output.
- Compatibility behavior must have a current consumer and explicit retirement posture. Remove dead
  or obsolete paths rather than preserving them by habit.
- Repository docs must distinguish implemented capability, local validation, mesh certification,
  release evidence, and production availability.
- Report-only technology-governance evidence is renewed only from an exact-main releasability
  dispatch with `make refresh-technology-governance-receipts RUN_ID=<run-id>`; the command verifies
  the source revision, governed workflow identity, exact-revision assertion, artifact identity,
  digest and expiry without changing the original assessment or claim boundary. See
  [Validation and CI](wiki/Validation-and-CI.md#renewing-report-only-technology-governance-receipts).
- Active source-product declaration, local implementation proof, live validator proof, repo-owned
  telemetry, and mesh certification are distinct states; trust telemetry proof currently covers
  exactly `PortfolioStateSnapshot:v1` and `DpmSourceReadiness:v1`; it is not blanket certification.
- `PortfolioStateSnapshot:v1` publishes independent portfolio and market-data dates through
  `source_provenance`, including carried-forward evidence. Do not let consumers synthesize these
  dates from request or wall-clock time.
- Managed-gate orchestration failures emit a credential-redacting
  `lotus.managed-gate-orchestration-failure.v1` receipt with `non_certifying_failure` posture; a
  failure receipt is operational evidence, never certification.
- Persistence-consumer JSON/schema rejection logs carry bounded structured error identity and
  correlation only. Do not restore raw `ValidationError` tracebacks, input values, validator
  messages or serialized payloads; the shared formatter is a backstop, not the primary boundary.
  Malformed broker payload evidence redacts at most 16,384 retained characters, appends an explicit
  truncation marker, and reuses that result for the 1,500-character durable excerpt.
- The governed producer capacity profile materializes 10,000 positions and reports
  publication-age p50/p95/p99 plus processed-event throughput. Keep
  `outbox-capacity-profile.v1.json` and
  `outbox-capacity-profile-guard` aligned so a bounded sample cannot be mistaken for total producer
  throughput.
- The derived-state bank-day profiles scrape bounded database-operation histograms from transaction
  processing, valuation orchestration, position valuation, and portfolio derived-state. Preserve
  the stable runtime identity on every sample and fail closed when a required runtime hot path is
  absent; cumulative duration and mean are attribution evidence, not percentile or saturation
  proof.

## Performance-load diagnostic practice

The existing processing port owns optional transient capture; its transaction-processing
infrastructure sink is registered with the UOW and enabled only by the owned load gate's fixed
private file before seed delivery. Missing enablement is cached disabled once per process.
The POSIX transport uses an exclusively created owner-only mode0700 directory in the isolated
worker, mode0600 regular files, owner checks and no-follow directory-relative descriptors.
Existing directory reuse and unsafe file targets are refused; snapshot replacement is exclusive
and remains off-loop. Windows lifecycle mocks do not certify these POSIX filesystem controls.
Exact load tenant/portfolio, finite enable age and random run generation bound admission.
The existing setup SQL roundtrip optionally reads typed backend PID/birth/database identity;
disabled SQL is unchanged, and phase changes issue no SQL or filesystem calls. Twenty records
and 16KiB bound the private snapshot. Active holders survive long windows/capacity pressure;
completed records have 120-second retention. One half-second background publisher uses a
single off-loop write at a time. Diagnostic callback faults use one saturating process-local
counter with no financial-path IO, logs or metric labels. Capture errors do not replace financial exceptions or
cancellation; no hard filesystem latency bound is claimed. Task-affine handles reject inherited
child-task and stale-generation updates. Collector projection requires fresh same-run and
unique backend-birth/database matches; an in-progress phase is not an exact Python await.
The separate replay-reader/publisher session is outside this instrumentation and remains
unobserved. No financial ordering, locks, source authority, commit boundary, runtime topology,
dependency or SLO changes are part of this diagnostic slice.
Consumer metrics use actual production TXNPROC/TXNREPLAY service/topic/group tuples, with
explicit no-matching-sample reasons and unchanged privacy/finite/input/output/row limits.
Focused tests additionally live in `tests/unit/scripts/test_load_phase_diagnostics.py` and the
transaction-processing infrastructure's `test_diagnostics.py`; their mocks do not certify PG,
Kafka, filesystem latency or deployed worker identity. See the Operations Runbook for the
enablement and unknown-evidence limits.

Replay completion reports retain baseline/target/final bounded scrape states and ordered request
receipts; missing samples never become measured zero, and observed counter decreases or changed
counter-creation or same-exposition process-birth identity fail completion closed. Missing producer
birth cannot certify continuity. Completion scrape input is independently bounded to 1MiB; the
collector's 32KiB projected-output budget is unchanged. Partial accepted counts do not manufacture
accepted IDs or durable completion receipts. Replay polling checks completion before diagnostics.
The first qualified same-birth, unmet-target poll at or beyond the profile SLO requests one
active snapshot; missing/reset continuity cannot launch it. Later completion/timeout cannot
replace it, and an unavailable attempt is not retried. A finite owned receiver plus deadline
timer drains pipe backpressure and stops the child without waiting for report finalization;
cleanup time is reserved within the original six-second request/collection budget. The child
is pre-armed idle before any profile workload or measured clock; the pending callback only
records the boundary and signals an existing Event, never starts a process or waits for receipt.
Preparation readiness has a separate allowance, and native `Process.start()` has no hard
preparation-latency guarantee. Idle custody has a separate finite allowance derived from existing
batch/sleep/drain limits; it does not extend those limits. Expired, failed or unused preparations
cannot probe and are retired without manufacturing an active-boundary record. Actual setup,
idle, request and collection timing remain separate; absent request/child timing is null.
Owned threads/child/pipe custody
is finalized before teardown, with failures explicit rather than masking the enforcing verdict.
Request lateness, launch/custody overhead and available child observation delay are diagnostic
metadata, not an exact boundary timestamp or zero-overhead claim. When no active attempt exists,
the original timeout collector remains. Completion deadline, finite elapsed time and independent
180-second full-profile verdict remain unchanged. Focused controls live in
`tests/unit/scripts/test_load_active_diagnostics.py` and the existing load-gate/phase suites;
spawn/pipe controls are mechanism evidence, not PostgreSQL, financial or full-load qualification.
Database PID observations require backend birth identity and lock OIDs; NULL relation is not an
inferred table. Managed-container lookup uses plain Docker label-filtered `ps`, not a Compose
plugin process; inspect verifies exact project/service/published port. Its birth/init-PID metadata
is distinct from an actual
application-worker PID or await, which remain MISSING unless measured. Raw SQL is never exported;
the bounded collector retains only whitelisted structure with literal/unknown-token redaction and
ambiguous-syntax refusal. This is diagnostic supportability, not a financial/runtime cause proof.

Diagnostic consumer metrics also have a separate 1MiB input bound, public known-label filtering
and finite-value admission; malformed/private/nonfinite input is unavailable, not zero.
Read-only, nonjoining Kafka offsets sample raw, persisted and replay-request groups round-robin
within 20 rows, with per-group failures and truncation explicit. PostgreSQL lock observations
prioritize blocker heads/edges, qualify both PID births against the preceding activity sample,
and report row truncation; incomplete or stale births do not certify edges. Application
task/backend mapping remains MISSING. Substantial lock SQL changes require scoped native
PostgreSQL proof after source/test freeze and runtime authorization, beyond mocks/query text.

`scripts/operations/performance_load_gate.py` owns partial-report publication at its original
exception boundary. `transaction_processing_load_support.py` owns supported acknowledgement
lineage and the shared completion/fixture probes. The existing performance package owns
`scripts/operations/performance/load_completion_diagnostics.py` for isolated bounded process,
database, metric and Kafka diagnostics. Main imports it directly; shared support has no reverse
import or compatibility alias. Keep
portfolio aggregate claims separate from prefix domain counts; replay not-run, missing evidence,
budget exhaustion and unconfirmed child cleanup cannot become successful or zero observations.
Never relax economics, input cardinality, financial admission, ordering or drain SLOs to collect
diagnostics. Preserve the original nonzero exception even if collection/publication fails.
Use `tests/unit/scripts/test_performance_load_gate.py` for focused native script/report/process
proof; its mocks do not certify PostgreSQL/Kafka semantics, actual metric exposition availability,
pipeline cause or main readiness. See `docs/operations/bank-day-load-scenario.md` for operator
budgets and supportability limits.

Diagnostic clients must use `portfolio_common.db.create_sync_database_engine` and
`portfolio_common.connection_security.build_kafka_connection_config`. Retain inherited validated
security/trust, governed operator identity and `NullPool`; diagnostic profile limits belong only
to the private child. The supported connection-timeout minimum is two seconds. Do not substitute
raw DBAPI connections, plaintext defaults or constructor aliases to evade source-wide guards.
For script/client slices, run these existing checks from the Core root before publication in
addition to focused tests and checks on every changed file; default `src` checks omit scripts:

```powershell
python scripts/development/repository_python.py -m pytest tests/unit/contracts/test_app_local_runtime_security_contract.py::test_direct_kafka_clients_cannot_bypass_shared_transport_security tests/unit/libs/portfolio-common/test_db.py::test_database_engines_use_governed_factory -q
```

```bash
python scripts/development/repository_python.py -m pytest tests/unit/contracts/test_app_local_runtime_security_contract.py::test_direct_kafka_clients_cannot_bypass_shared_transport_security tests/unit/libs/portfolio-common/test_db.py::test_database_engines_use_governed_factory -q
```

## Portfolio Source Observation Practice

The `PortfolioFinancialSourceObservations` product retains independent cash-availability and
funding/investment assertions. Submission requires a verified identity, the exact family write
capability, and a separate server-owned tenant/portfolio/producer grant; deployed grants are empty.
Admission does not qualify a bank feed. Amounts remain independent nullable exact decimals and
flags remain independent nullable booleans; no available-cash formula or lifecycle inference is
owned here. See [the methodology](docs/methodologies/source-data-products/portfolio-financial-source-observations.md).

The dedicated ingestion creation callback appends immutable facts, advances scoped heads and
completes the new receipt in one supplied local transaction. It does not commit independently,
queue a worker or publish directly. Existing asynchronous reference ingestion remains unchanged.
Original reads require all four immutable pins; latest-restated selection is explicit. QCP reads
both independently selected families in one statement snapshot, but always reports authoritative
state and cross-product compatibility as unavailable. Scope/currency locks are separate from
source-record revision locks; corrections cannot change their authority dimensions.

QCP projects the same bounded product/family reasons into the existing generic degradation
summary with UNAVAILABLE severity. Eligible diagnostic facts remain unchanged; absent evidence
is not zero or false, and request/serving time is not authoritative source-time evidence.

Exact fingerprint replay is read-only after verified producer/capability/tenant admission and
requires a completed receipt with its completion timestamp before bypassing new-write mode/rate
controls. Completed records count as processed capacity, not backlog, and remain excluded from
asynchronous queue-latency samples without removing their completion timestamps. Interval overlap uses an
explicit nullable upper bound and half-open finite boundaries; no date sentinel substitutes for
infinity. Four bounded actual c178 downgrade/TRUNCATE barrier nodes are routed to
`critical-db-coverage` as well as the complete owning query-authority proof module.

Owning PostgreSQL tests derive a capability-validated, UUID-named schema from the native
`db_engine` lease and apply the actual migration there. Parent identity sequences are local to
that schema; teardown verifies the database, session owner and schema marker before dropping
only the owned namespace. They do not use shared `clean_db` or optional-URL skip fallbacks.
Populated history blocks
downgrade and TRUNCATE, including parent cascades. Empty truncate is supported only under
READ COMMITTED; stale transaction-fixed snapshots fail closed. Unit/collection evidence cannot
replace the actual PostgreSQL rollback, correction-race and migration-barrier controls.

## Context Maintenance Rule

Update this file only when current Core ownership, architecture, financial invariants, task routes,
canonical commands, or completion evidence changes. Keep issue status, PR history, commit diaries,
and temporary blockers in GitHub.

## Cross-Links

1. [README](README.md)
2. [Documentation index](docs/README.md)
3. [Architecture index](docs/architecture/README.md)
4. [Supported Features](wiki/Supported-Features.md)
5. [API Surface](wiki/API-Surface.md)
6. [Operations Runbook](wiki/Operations-Runbook.md)
7. [Validation and CI](wiki/Validation-and-CI.md)
8. [Platform context reference map](https://github.com/sgajbi/lotus-platform/blob/main/context/CONTEXT-REFERENCE-MAP.md)
9. [Platform engineering context](https://github.com/sgajbi/lotus-platform/blob/main/context/LOTUS-ENGINEERING-CONTEXT.md)
