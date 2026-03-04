# RFC Relocation Plan

Generated: `2026-03-04`

Purpose:
- Assign explicit destination ownership for RFCs that no longer belong in `lotus-core`.
- Avoid “no-home” RFC drift.
- Keep migration lineage clear while new app boundaries are established.

## Approved Naming Decision

- New destination app for intelligence/NBA/NLG features: `lotus-intelligence`
- Existing advisory app remains: `lotus-advise`

Boundary intent:
1. `lotus-intelligence`: recommendation intelligence, insight/NLG generation, active-learning/model lifecycle.
2. `lotus-advise`: advisor-facing workflows, UX orchestration, human-in-the-loop interactions.

## Relocation Candidates

| RFC | Current lotus-core classification | Proposed target home | Rationale |
| --- | --- | --- | --- |
| RFC-009 | Archived / no longer relevant | `lotus-intelligence` | Insight/NLG pipeline ownership is intelligence-domain, not core ledger/runtime. |
| RFC-011 | Archived / no longer relevant | `lotus-intelligence` | NBA generation/scoring/feedback loop belongs to intelligence-domain services. |
| RFC-014 | Archived / no longer relevant | `lotus-intelligence` | Active-learning and model lifecycle governance is ML platform scope. |
| RFC-015 | Archived / no longer relevant | `lotus-intelligence` (with `lotus-advise` integration) | Hyper-personalization logic is intelligence-domain; advisor workflow consumption belongs in lotus-advise. |

## Operational Rule

Until migration is complete:
1. Keep archived RFC pointers in `lotus-core`.
2. New changes for these RFCs must be authored in `lotus-intelligence` (or cross-repo contract RFCs), not in `lotus-core`.
3. `lotus-core` maintains only canonical data/integration contracts required by these downstream domains.
