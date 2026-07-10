# CR-1440: Transaction Processing Composition

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Objective

Provide one production dependency-composition path for the combined use case without letting
runtime/delivery code construct legacy calculator consumers or concrete repositories.

## Change

- Added a typed SQLAlchemy UoW factory that creates a fresh UoW per message.
- Added `build_process_transaction_use_case()` using the repository-standard async session factory.
- Reuse one delivery-free cost workflow and one cashflow workflow/cache across message attempts.
- Keep calculator imports in infrastructure composition; runtime and delivery depend on the target
  use case and consumer contracts only.

## Performance And Scalability

Policy collaborators and the guarded cashflow rule cache are not rebuilt per transaction. Database
sessions remain per-UoW and are always closed. Scaling remains controlled by consumer partitions,
bounded in-flight work, DB pool capacity, and portfolio-key ordering.

## Compatibility

The builder is not yet registered in the runtime manager. Existing deployables, consumers, groups,
images, and topics are unchanged.

## Evidence

- Target-service unit pack: 35 passed.
- Tests prove fresh UoWs, reused plain workflows, no Kafka state on workflows, and repository-native
  session-factory injection.
- Focused MyPy/Ruff, modularity/boundary/strict architecture, full source dead-code, and diff gates
  passed.

## Same-Pattern Decision

Runtime composition must call this builder. Do not construct repositories, sessions, or calculator
consumers in the Kafka delivery class or runtime manager.

No README/wiki change is required because runtime topology has not switched.
