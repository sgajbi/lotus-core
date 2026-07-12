# CR-067 Contract Tooling Quiet Mode Review

## Scope

- `src/libs/portfolio-common/portfolio_common/logging_utils.py`
- `scripts/openapi_quality_gate.py`
- `scripts/api_vocabulary_inventory.py`
- `tests/unit/libs/portfolio-common/test_logging_utils.py`

## Findings

- The OpenAPI and API vocabulary scripts were healthy, but their output remained noisy because importing the app modules initialized JSON logging at `INFO`.
- That made success-path contract gates harder to scan and diluted their usefulness in CI and local review loops.

## Actions taken

- Added a tooling-only quiet flag in `logging_utils.setup_logging()`:
  - `LOTUS_TOOLING_QUIET=1` now drives the root logger to `ERROR`
- Set that flag by default in:
  - `scripts/openapi_quality_gate.py`
  - `scripts/api_vocabulary_inventory.py`
- Added unit coverage proving quiet-mode and normal-mode logger levels.

## Result

- Contract-tooling runs stay focused on gate results instead of routine startup noise from imported services.

## Evidence

- `python -m pytest tests/unit/libs/portfolio-common/test_logging_utils.py -q`
- `python scripts/openapi_quality_gate.py`
- `python scripts/api_vocabulary_inventory.py --validate-only`
