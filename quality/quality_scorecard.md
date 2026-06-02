# lotus-core Quality Scorecard

Status: Initial scorecard baseline on 2026-06-02.

| Category | Current Baseline | Target Direction |
| --- | --- | --- |
| Python code size | 1,040 files / 213,290 lines under `src` and `tests` | Reduce generated/duplicated quality surface and split large modules |
| Ruff findings | 0 findings under `python -m ruff check . --statistics`; enforced by `make quality-ruff-gate` and the quality-baseline Ruff regression job | Keep Ruff clean and add format enforcement only after the remaining format baseline is cleaned |
| Ruff format | 68 files still require formatting under `python -m ruff format --check .` after CR-861 | Ratchet in bounded batches, then enforce a format gate once clean |
| Test collection | 3,575 collected; import/plugin blockers fixed; full all-suite collection stops at governed mixed-runtime guard | Run runtime-separated collection lanes cleanly |
| Coverage | Not measured in initial baseline due collection errors | Add line and branch coverage artifacts after collection is clean |
| Complexity | Average `A (3.01)` with several D/E hotspots | No new D/E hotspots; refactor existing hotspots by domain priority |
| Maintainability | Most files A/B; selected C hotspot in OpenAPI enrichment | No new C/D maintainability files |
| Dead code | Not measured locally; tool missing | Add vulture report-only CI |
| Dependency usage | Not measured locally; tool missing | Add deptry report-only CI |
| Security | Not measured locally; bandit command missing | Add bandit and pip-audit report-only CI |
| Architecture boundaries | Existing make gate plus import-linter scaffold | Convert report-only contract into regression gate |
| OpenAPI governance | Existing make gate plus spectral scaffold | Publish spectral/OpenAPI reports |
| Documentation | New top-level governance docs scaffolded; CR-847 records collection/build-artifact cleanup | Keep docs implementation-backed and current |
