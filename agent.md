# Lotus Core Agent Operating Notes

## RFC Review Standard

Use skill: `lotus-rfc-review-loop` for any RFC audit, re-documentation, or standardization request.

Do not attempt full-repository RFC review in one pass.
Always run in iterative loops with batch size `3-7` RFCs.

## Loop Contract (Required)

1. Refresh index:
   - `python C:/Users/Sandeep/.codex/skills/lotus-rfc-review-loop/scripts/rfc_inventory.py --rfc-dir docs/RFCs --output docs/RFCs/RFC-INDEX.md`
2. Select next batch (highest risk/recent first).
3. Review each RFC with evidence from `src/`, `tests/`, OpenAPI, and runbooks.
4. Classify each RFC:
   - Fully implemented and aligned
   - Partially implemented (requires enhancement)
   - Outdated (requires revision)
   - No longer relevant to this repository
5. Standardize reviewed RFCs to the template in:
   - `C:/Users/Sandeep/.codex/skills/lotus-rfc-review-loop/references/rfc-standard-template.md`
   - Preserve original requirements and acceptance criteria; do not reduce RFCs to brief summaries.
   - Include requirement-to-implementation traceability and design reasoning/trade-offs.
6. Update `docs/RFCs/RFC-INDEX.md` fields:
   - Review Status
   - Implementation Classification
   - Evidence
   - Next Actions
7. Update `docs/RFCs/RFC-DELTA-BACKLOG.md` with validated deltas only:
   - verify if already implemented
   - assess if still relevant under current app/platform state
   - mark `open` / `done` / `deferred` with evidence
8. Publish prioritized actions (P0/P1/P2) for next engineering increment.

## Status Vocabulary

Use only:
- Draft
- Approved
- Implemented
- Partially Implemented
- Deprecated
- Archived

## Cross-App Alignment

When RFCs involve cross-app ownership (lotus-performance, lotus-risk, lotus-platform, lotus-manage):
- Keep lotus-core scope explicit.
- Mark non-core RFCs as archive/move candidates in the index.
- Link destination repo and owner in `Next Actions`.
- For archived RFC files, keep historical rationale and migration context as a durable pointer.

For intelligence/advisory RFC relocation:
- Use `lotus-intelligence` as destination app for NBA/NLG/active-learning/personalization engine RFCs.
- Keep `lotus-advise` as advisor workflow/UX owner (consumer/orchestrator), not engine owner.
- Reference `docs/RFCs/RFC-RELOCATION-PLAN.md` for approved mapping.

## Documentation Fidelity Rule

Every standardized RFC must clearly capture:
1. What was originally requested.
2. What is implemented now (with code/test evidence).
3. Why current implementation/design aligns or diverges.
4. What deltas remain and why they still matter (or should be deferred).
