# lotus-core Quality Scorecard

Status: Initial scorecard baseline on 2026-06-02.

| Category | Current Baseline | Target Direction |
| --- | --- | --- |
| Python code size | 1,040 files / 213,290 lines under `src` and `tests` | Reduce generated/duplicated quality surface and split large modules |
| Ruff findings | 0 findings under `python -m ruff check . --statistics`; enforced by `make quality-ruff-gate` and the quality-baseline Ruff regression job | Keep Ruff lint regression-free while broader gates continue to ratchet |
| Ruff format | Clean and enforced by `make quality-ruff-format-gate` plus the quality-baseline Ruff format job after CR-866 | Keep Ruff formatting regression-free while broader gates continue to ratchet |
| Typecheck | Clean for the configured query-service DTO/router scope under `make typecheck`; enforced by the quality-baseline typecheck job after CR-869 | Expand typed source scope progressively without weakening the gate |
| Test collection | 3,575 collected; import/plugin blockers fixed; full all-suite collection stops at governed mixed-runtime guard | Run runtime-separated collection lanes cleanly |
| Coverage | Not measured in initial baseline due collection errors | Add line and branch coverage artifacts after collection is clean |
| Complexity | Average `A (3.01)` with several D/E hotspots | No new D/E hotspots; refactor existing hotspots by domain priority |
| Maintainability | Most files A/B; selected C hotspot in OpenAPI enrichment | No new C/D maintainability files |
| Dead code | Not measured locally; tool missing | Add vulture report-only CI |
| Dependency usage | Not measured locally; tool missing | Add deptry report-only CI |
| Security | Bandit baseline measured after CR-869: 17 findings under `python -m bandit -r src -c pyproject.toml` (5 low, 11 medium, 1 high); remains report-only | Fix or govern findings before enforcement; start with high-confidence MD5 fingerprint finding |
| Architecture boundaries | Existing strict architecture guard plus 2 kept import-linter contracts enforced by `make quality-import-boundary-gate` after CR-867 | Add focused import contracts as additional ownership boundaries stabilize |
| OpenAPI governance | Existing OpenAPI quality and API vocabulary gates promoted into the quality-baseline API governance job after CR-868 | Keep API governance regression-free while spectral remains report-only until a stable generated-spec artifact exists |
| Documentation | New top-level governance docs scaffolded; CR-847 records collection/build-artifact cleanup | Keep docs implementation-backed and current |
