# CR-850: Governance Helper Import Order Lint Ratchet

Status: Hardened on 2026-06-02.

## Finding

After the Alembic import-order cleanup, the Ruff baseline still carried 32 import-order findings.
Twelve were concentrated in governance scripts, database tools, and shared supportability helpers:
RFC-0082/RFC-0083 guard scripts, domain-product validation tooling, database maintenance tools,
and the ingestion, reconstruction, and reconciliation helper modules.

## Change

Ran Ruff import organization against the bounded governance-helper set:

1. `scripts/`,
2. `tools/`,
3. `portfolio_common.ingestion_evidence`,
4. `portfolio_common.reconciliation_quality`,
5. `portfolio_common.reconstruction_identity`.

Full Ruff findings are down from 283 to 271 after this slice.

## Boundary Preserved

This change does not alter:

1. guard validation logic,
2. source-data product or route-family contracts,
3. supportability helper behavior,
4. database maintenance behavior,
5. runtime service behavior,
6. API contracts or database schema.

## Wiki Decision

No repo-local `wiki/` source update is included. This is import-order normalization for existing
governance/helper code and does not change operator-facing truth.

## Validation

Local validation passed for the slice:

1. `python -m ruff check scripts tools src/libs/portfolio-common/portfolio_common/ingestion_evidence.py src/libs/portfolio-common/portfolio_common/reconciliation_quality.py src/libs/portfolio-common/portfolio_common/reconstruction_identity.py --select I001`,
2. `python -m ruff check . --statistics`,
3. focused guard/helper unit tests,
4. git diff whitespace checks.
