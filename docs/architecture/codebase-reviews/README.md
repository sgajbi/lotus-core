# Codebase Review Records

This directory owns individual `CR-*.md` review-evidence records.

Use the [codebase review ledger](../CODEBASE-REVIEW-LEDGER.md) to find current status, remediation,
validation evidence, and follow-up work. Use the
[codebase review playbook](../CODEBASE-REVIEW-PLAYBOOK.md) when creating or updating a record.

## Records Are Point-In-Time Evidence

Each `CR-*.md` record documents what was reviewed at the commit it was written against. Its
`Reviewed on:` paths, line references, and quoted code describe the tree **as it stood then**, not
as it stands now.

A record may therefore cite modules and services that have since been renamed, consolidated, or
retired — for example the pre-consolidation calculator services, or `portfolio_common` modules that
have since moved behind service-owned packages. That is expected and correct: rewriting those
citations to today's paths would falsify the evidence the record exists to preserve.

Consequences for readers and tooling:

- **Do not "repair" stale-looking paths in `CR-*` records or in the ledger.** A link checker or
  reference sweep will flag them; they are history, not drift.
- **Do not read a record as current architecture guidance.** For the state of the system today, use
  the [architecture README](../README.md) and the service documentation; for the current status of a
  finding, use the [ledger](../CODEBASE-REVIEW-LEDGER.md).
- **A superseded record is not edited into agreement with a later one.** The ledger carries the
  current position; the records carry the trail that produced it.

## Repository Contract

1. Name each record `CR-<reserved-id>-<domain-description>.md`.
2. Keep status and summary truth in the ledger; keep detailed evidence in the record.
3. Keep links between records relative to this directory.
4. Do not place `CR-*` records directly in `docs/architecture/`.
5. Update affected records, the ledger, tests, and documentation truth in the same slice.
