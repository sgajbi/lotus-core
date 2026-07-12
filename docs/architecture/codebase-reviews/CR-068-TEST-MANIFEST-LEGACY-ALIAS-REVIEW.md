# CR-068 Test Manifest Legacy Alias Review

## Scope

- `scripts/test_manifest.py`
- `tests/unit/services/query_service/test_test_manifest.py`

## Findings

- The manifest still carried backward-compatible suite aliases such as:
  - `buy-rfc`
  - `sell-rfc`
  - `dividend-rfc`
  - `interest-rfc`
  - `fx-rfc`
  - `portfolio-flow-bundle-rfc`
- The project direction is now explicit: no legacy support unless it protects a real live compatibility contract.
- These aliases were local compatibility residue only. They blurred the canonical suite vocabulary without protecting any live external caller.

## Actions taken

- Removed the legacy suite aliases from `scripts/test_manifest.py`.
- Removed the corresponding alias-profile mappings from `SUITE_ENV_PROFILE`.
- Updated the manifest unit tests to use the canonical suite names:
  - `transaction-sell-contract`
  - `transaction-fx-contract`

## Result

- The test manifest now exposes one canonical suite vocabulary only.

## Evidence

- `python -m pytest tests/unit/services/query_service/test_test_manifest.py -q`
- `python scripts/test_manifest.py --suite transaction-fx-contract --print-args`
