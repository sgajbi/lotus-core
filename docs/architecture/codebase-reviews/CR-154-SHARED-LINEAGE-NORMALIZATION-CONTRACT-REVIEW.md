# CR-154 - Shared Lineage Normalization Contract Review

## Scope
- shared lineage sentinel handling
- write-plane Kafka header emission
- replay publication
- HTTP exception/audit payload normalization

## Finding
Sentinel lineage normalization (`"<not-set>"`, empty string, missing values) had been implemented repeatedly across transport, replay, write-plane, and audit code. That duplicated a banking-critical contract and created drift risk: future fixes would have to land in many places or behavior would diverge again.

## Fix
- Added `normalize_lineage_value(...)` to `portfolio_common.logging_utils`.
- Replaced local sentinel checks in:
  - ingestion request lineage
  - ingestion Kafka header construction
  - HTTP exception correlation handling
  - shared Kafka DLQ emission
  - replay publication
  - query/control-plane enterprise audit payloads
  - position replay outbox correlation handling
- Added direct unit proof for the shared helper and revalidated the affected write-plane, replay, transport, and audit slices.

## Result
Lineage sentinel handling is now owned by one shared contract instead of copy-pasted conditionals. That reduces drift, keeps the code easier to reason about, and makes future lineage fixes land once.
